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
    for mm in (m if isinstance(m, (list, tuple)) else [m]):
        me.materials.append(mm)
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


def box(name, c, size, m, bevel=0.015, seg=1, rot=None):
    c, h = Vector(c), Vector(size) / 2
    q = Euler([math.radians(a) for a in rot]).to_matrix() if rot else None

    def fn(sx, sy, sz):
        p = Vector((sx * h.x, sy * h.y, sz * h.z))
        return c + (q @ p if q else p)
    return shaped_box(name, fn, m, bevel, seg)


def bbox(name, lo, hi, m, bevel=0.015, seg=1):
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


def prism(name, pts, x0, x1, m, bevel=0.02, seg=2, angle=30, smooth=True):
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
    return finish_obj(name, bm, m, smooth=smooth, bevel=bevel, seg=seg, angle=angle)


def xprism(name, pts, y0, y1, m, bevel=0.02, seg=2, angle=30, smooth=True):
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
    return finish_obj(name, bm, m, smooth=smooth, bevel=bevel, seg=seg, angle=angle)


def strip(name, pts, offset, m, facing, smooth=False):
    """Open ribbon: a polyline swept by `offset` (no caps); faces turned toward `facing`."""
    bm = bmesh.new()
    A = [bm.verts.new(p) for p in pts]
    B = [bm.verts.new(p + offset) for p in pts]
    for i in range(len(pts) - 1):
        bm.faces.new([A[i], A[i + 1], B[i + 1], B[i]])
    bm.normal_update()
    for f in bm.faces:
        if f.normal.dot(facing) < 0:
            f.normal_flip()
    return finish_obj(name, bm, m, smooth=smooth)


def shoulder_prism(name, pts, hw, m, inset=0.04, drop=0.03, z_lo=0.4, z_hi=0.6, bevel=0.03, seg=2, angle=30):
    """Side profile extruded across +-hw with rounded-off shoulders: the outer faces sit `drop` lower
    near the top (ramping in from z_lo to z_hi) and `inset` in from the centre slab."""
    def lowered(z):
        t = max(0.0, min(1.0, (z - z_lo) / max(z_hi - z_lo, 1e-6)))
        return z - drop * t
    secs = []
    for x, low in ((-hw, True), (-hw + inset, False), (hw - inset, False), (hw, True)):
        secs.append([(x, y, lowered(z) if low else z) for y, z in pts])
    return loft(name, secs, m, bevel=bevel, seg=seg, angle=angle, smooth=lambda p: len(p.vertices) == 4)


def loft(name, sections, m, bevel=0.0, seg=2, angle=30, caps=True, smooth=True, face_mat=None):
    """Join closed loops of equal vertex count (lists of 3D points) with quads.
    m may be a list of materials with face_mat(k, span) -> material index for the quad leaving point k."""
    bm = bmesh.new()
    rows = [[bm.verts.new(Vector(p)) for p in s] for s in sections]
    n = len(sections[0])
    for span, (A, B) in enumerate(zip(rows, rows[1:])):
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new([A[i], A[j], B[j], B[i]])
            if face_mat:
                f.material_index = face_mat(i, span)
    if caps:
        bm.faces.new(rows[0][::-1])
        bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=smooth, bevel=bevel, seg=seg, angle=angle)


def rrect(cx, cz, hw, hh, r, n=2, top=()):
    """Rounded rectangle loop in the (x, z) plane, CCW, 4*(n+1) points (+ extra points along the top
    edge at the given fractions of the half width, listed from +x to -x)."""
    pts = []
    for (sx, sz, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ccx, ccz = cx + sx * (hw - r), cz + sz * (hh - r)
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((ccx + math.cos(a) * r, ccz + math.sin(a) * r))
        if sx == 1 and sz == 1:
            pts += [(cx + f * (hw - r), cz + hh) for f in top]
    return pts


def section(y, loop2d, taper_top=0.0):
    """Lift an (x, z) loop into 3D at y."""
    return [(x, y, z) for x, z in loop2d]


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


def lathe(name, prof, m, steps=16, out=(1.0, 0.0), phase=0.0, face_mat=None):
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
            if face_mat:
                f.material_index = face_mat(i, k)
            if first is None:
                first = f
    bm.normal_update()
    c = first.calc_center_median()
    radial = Vector((0, c.y, c.z)).normalized()
    hint = Vector((out[0], 0, 0)) + radial * out[1]
    if first.normal.dot(hint) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    return finish_obj(name, bm, m, smooth=True)


def vlathe(name, prof, base, m, steps=16, face_mat=None, phase=0.0):
    """Vertical surface of revolution: prof = [(height, radius), ...] about the Z axis through base."""
    ob = lathe(name, prof, m, steps=steps, out=(0.0, 1.0), phase=phase, face_mat=face_mat)
    ob.data.transform(Matrix.Translation(Vector(base)) @ Euler((0, -pi / 2, 0)).to_matrix().to_4x4())
    return ob


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
    side = [(-0.86 * w, rim_r), (-w, rim_r + sh * 0.5), (-0.9 * w, Rc - sh * 0.1)]
    crown = []
    if tread == "road":
        # circumferential V-grooves cut straight into the profile
        gs = {1: [0.0], 2: [-0.3, 0.3], 3: [-0.42, 0.0, 0.42]}[grooves]
        crown.append((-0.62 * w, Rc))
        for g in gs:
            crown += [((g - 0.07) * w, Rc), (g * w, Rc - depth), ((g + 0.07) * w, Rc)]
        crown.append((0.62 * w, Rc))
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
            cyl(name + "_Hub", (hub_x - 0.005, 0, 0), (hub_x + 0.035, 0, 0), rim_r * 0.2, cap or CHROME,
                seg=10, r1=rim_r * 0.15)
            for i in range(lugs):
                a = 2 * pi * (i + 0.5) / lugs
                p = Vector((hub_x, math.cos(a) * rim_r * 0.24, math.sin(a) * rim_r * 0.24))
                cyl("Lug", p, p + X * 0.016, 0.009, CHROME, seg=4, caps=(False, True), r1=0.007)
            if style == "truck" and lugs > 6:
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
            for i in range(8):
                a = 2 * pi * i / 8
                bolt((lip_x + 0.02, math.cos(a) * rim_r * 0.92, math.sin(a) * rim_r * 0.92), X, r=0.014)


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
    r, seg_a, seg_b = 0.013 * R / 0.075, 12, 4
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
            bevel=0.0)
    box("Cushion", c + Vector((0, 0, -cushion_t / 2)), (w, d, cushion_t), m, bevel=0.022, seg=1)
    box("SeatBack", c + Vector((0, d / 2 + 0.02, back_h / 2 - 0.01)), (w * 1.02, 0.07, back_h), m, bevel=0.025, seg=1,
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
    corners = []
    for o in objs:
        if o.type == "MESH":
            mw = o.matrix_world
            vs = o.data.vertices
            corners += [mw @ vs[i].co for i in range(0, len(vs), 3)]
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
            if o.name.replace("_", "").startswith(part):
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


def shutter(s, x, y0, y1, z0, z1, m, rib=0.065, depth=0.008):
    """Roll-up compartment door on the side face x (s = side sign): corrugated slats."""
    n = max(2, int(round((z1 - z0) / rib)))
    h = (z1 - z0) / n
    pts = [(x - s * 0.002, z0)]
    for k in range(n):
        z = z0 + k * h
        pts += [(x + s * depth * 0.3, z + h * 0.02), (x + s * depth, z + h * 0.9)]
    pts.append((x - s * 0.002, z1))
    strip("Shutter", [Vector((px, y0, pz)) for px, pz in pts], Y * (y1 - y0), m, Vector((s, 0, 0)))
    bbox("ShutterBar", (min(x, x + s * 0.03), y0 + 0.04, z0 + 0.025), (max(x, x + s * 0.03), y1 - 0.04, z0 + 0.05),
         CHROME, bevel=0.0)


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
        bbox("Rail", (s * 0.34, -1.40, 0.17), (s * 0.24, 1.46, 0.29), BLACK, bevel=0.0)
    cyl("AxleF", (-FT, FY, WR), (FT, FY, WR), 0.045, BLACK, seg=6, caps=(False, False))
    cyl("AxleR", (-RT, RY, WR), (RT, RY, WR), 0.06, BLACK, seg=6, caps=(False, False))
    cyl("Diff", (0, RY - 0.08, WR), (0, RY + 0.08, WR), 0.1, METAL, seg=8)
    cyl("FuelTank", (0.36, -0.42, 0.25), (0.36, 0.02, 0.25), 0.09, ALU, seg=10)

    # ---------- cab: hollow tub with big open side windows
    zb = 0.26
    prof = [(CAB_F, zb)] + arch(FY, WR, 0.365, zb, 7) + [(CAB_R, zb), (CAB_R, BELT), (CAB_F + 0.01, BELT)]
    for s in (-1, 1):
        prism("CabSide", prof, s * (HW - 0.05), s * HW, PAINT, bevel=0.02, seg=1)
        arc_band("FenderLip", FY, WR, 0.365, 0.395, s * (HW - 0.01), s * (HW + 0.03), BLACK, a0=0.05, a1=pi - 0.05,
                 steps=7, bevel=0.0)
        box("DoorHandle", (s * (HW + 0.008), -0.6, BELT - 0.05), (0.016, 0.08, 0.02), CHROME, bevel=0.0)
        bbox("CabStep", (min(s * (HW - 0.06), s * (HW + 0.03)), -0.56, 0.21),
             (max(s * (HW - 0.06), s * (HW + 0.03)), -0.46, 0.25), ALU, bevel=0.0)
        # gold Maltese cross with the company number on the door
        o = (s * HW, -0.86, 0.765)
        flat_poly("Cross", maltese(0.2), o, (0, s, 0), Z, GOLD)
        text("Num", "7", 0.085, o, (0, s, 0), Z, PAINT, font="Arial Black.ttf", lift=0.005)
    # front wall, floor, back wall, dash
    bbox("CabFront", (-HW, CAB_F, zb), (HW, CAB_F + 0.06, BELT), PAINT, bevel=0.025, seg=2)
    bbox("CabFloor", (-HW + 0.04, CAB_F + 0.05, FLOOR - 0.04), (HW - 0.04, CAB_R, FLOOR), BLACK, bevel=0.0)
    bbox("CabBack", (-HW, CAB_R - 0.05, zb), (HW, CAB_R, ROOF0 + 0.01), PAINT, bevel=0.02)
    bbox("Dash", (-HW + 0.05, CAB_F + 0.05, BELT - 0.14), (HW - 0.05, CAB_F + 0.17, BELT + 0.02), BLACK, bevel=0.02)
    for gx in (0.17, 0.31):
        disc("Gauge", (gx, CAB_F + 0.171, BELT - 0.04), Y, 0.026, GAUGE, seg=8)
    bbox("Doghouse", (-0.1, CAB_F + 0.15, FLOOR - 0.01), (0.1, -0.75, FLOOR + 0.12), PAINT, bevel=0.02)
    # windshield: raked pillars, split glass
    wb, wt = CAB_F + 0.02, CAB_F + 0.10
    for s in (-1, 1):
        beam("APillar", (s * (HW - 0.03), wb, BELT), (s * (HW - 0.03), wt, ROOF0), 0.06, 0.06, PAINT, bevel=0.012)
        beam("BPillar", (s * (HW - 0.03), CAB_R - 0.03, BELT), (s * (HW - 0.03), CAB_R - 0.03, ROOF0), 0.06, 0.06,
             PAINT, bevel=0.0)
        glass = [(s * 0.02, wb + 0.01, BELT + 0.02), (s * (HW - 0.06), wb + 0.01, BELT + 0.02),
                 (s * (HW - 0.06), wt + 0.01, ROOF0 - 0.02), (s * 0.02, wt + 0.01, ROOF0 - 0.02)]
        bm = bmesh.new()
        bm.faces.new([bm.verts.new(p) for p in glass])
        finish_obj("Windshield", bm, WINDOW, smooth=False)
        # west-coast mirror on a chrome arm
        tube("MirrorArm", [(s * (HW - 0.01), wb + 0.02, BELT + 0.04), (s * (HW + 0.1), wb - 0.02, BELT + 0.04),
                           (s * (HW + 0.1), wb - 0.02, BELT + 0.3)], 0.01, CHROME, sides=5, rad=0.04, n=1)
        box("Mirror", (s * (HW + 0.11), wb - 0.03, BELT + 0.17), (0.03, 0.08, 0.2), BLACK, bevel=0.0)
        box("MirrorGlass", (s * (HW + 0.11), wb - 0.05, BELT + 0.17), (0.022, 0.012, 0.18), CHROME, bevel=0.0)
    beam("CentrePost", (0, wb, BELT), (0, wt, ROOF0), 0.03, 0.03, BLACK, bevel=0.0)
    beam("Cowl", (-HW + 0.03, wb, BELT), (HW - 0.03, wb, BELT), 0.05, 0.05, BLACK, side=Z, bevel=0.0)
    # roof: white, overhanging visor, amber cab markers
    shaped_box("Roof", lambda sx, sy, sz: (sx * (HW + 0.01), (CAB_F + 0.06 if sz > 0 else CAB_F + 0.08) if sy < 0
               else CAB_R + 0.01, ROOF0 if sz < 0 else ROOF1), WHITE, bevel=0.035, seg=3)
    for x in (-0.36, -0.2, 0.2, 0.36):
        box("Marker", (x, CAB_F + 0.075, ROOF1 - 0.03), (0.05, 0.02, 0.025), AMBER, bevel=0.0)

    # ---------- interior: seats, column
    for x in (SEAT.x, -SEAT.x):
        seat_block(Vector((x, SEAT.y, SEAT.z)), 0.28, 0.26, SEATM, back_h=0.36, tilt=-6, base_h=SEAT.z - 0.07 - FLOOR,
                   base_m=BLACK, bolster=False)
    col_end = STEER - STEER_AX * 0.03
    cyl("Column", col_end - STEER_AX * 0.3, col_end, 0.02, BLACK, seg=6, caps=(False, True))

    # ---------- front: grille, lights, bumper
    gy = CAB_F - 0.004
    bbox("GrilleSurround", (-0.27, gy - 0.02, 0.38), (0.27, gy + 0.01, 0.80), CHROME, bevel=0.015)
    bbox("GrilleBack", (-0.23, gy - 0.025, 0.42), (0.23, gy - 0.01, 0.76), BLACK, bevel=0.0)
    for i in range(7):
        z = 0.44 + i * 0.05
        bbox("GrilleBar", (-0.23, gy - 0.03, z), (0.23, gy - 0.02, z + 0.016), CHROME, bevel=0.0)
    for s in (-1, 1):
        x = s * 0.40
        bbox("LampBox", (x - 0.09, gy - 0.02, 0.46), (x + 0.09, gy + 0.01, 0.76), CHROME, bevel=0.012)
        for z in (0.53, 0.68):
            cyl("Lamp", (x, gy - 0.02, z), (x, gy - 0.035, z), 0.05, HEADLIGHT, seg=10, r1=0.042, caps=(False, True))
        box("Turn", (x, gy - 0.02, 0.41), (0.12, 0.03, 0.04), AMBER, bevel=0.0)
        cyl("BumperLamp", (s * 0.47, CAB_F - 0.1, 0.27), (s * 0.47, CAB_F - 0.125, 0.27), 0.03, TAILLIGHT, seg=8,
            caps=(False, True))
        box("TowHook", (s * 0.2, CAB_F - 0.13, 0.21), (0.03, 0.06, 0.06), PAINT, bevel=0.0)
    shaped_box("Bumper", lambda sx, sy, sz: (sx * (0.56 if sy > 0 else 0.53), CAB_F - (0.12 if sy < 0 else 0.0),
                                             0.17 if sz < 0 else 0.35), CHROME, bevel=0.03, seg=2)
    text("FrontText", "FIRE RESCUE", 0.055, (0, CAB_F, 0.832), X, Z, GOLD, font="Arial Black.ttf", lift=0.004, res=1)

    # ---------- pump module: aluminium control panels, gauges, valves, gold caps
    PM0, PM1 = CAB_R, -0.20
    bbox("PumpHouse", (-BW, PM0, 0.28), (BW, PM1, BODY_TOP), PAINT, bevel=0.02, seg=2)
    for s in (-1, 1):
        x = s * BW
        bbox("PumpPanel", (min(x - s * 0.006, x + s * 0.008), PM0 + 0.03, 0.36),
             (max(x - s * 0.006, x + s * 0.008), PM1 - 0.03, 1.02), ALU, bevel=0.0)
        x += s * 0.008
        for (y, z, r) in [(-0.39, 0.92, 0.035), (-0.28, 0.92, 0.035), (-0.335, 0.80, 0.045)]:
            cyl("GaugeRim", (x, y, z), (x + s * 0.018, y, z), r, CHROME, seg=10, caps=(False, False))
            disc("GaugeFace", (x + s * 0.012, y, z), (s, 0, 0), r * 0.9, GAUGE, seg=10)
        for y in (-0.40, -0.27):
            cyl("Outlet", (x, y, 0.52), (x + s * 0.06, y, 0.52), 0.035, CHROME, seg=8, caps=(False, False))
            cyl("OutletCap", (x + s * 0.06, y, 0.52), (x + s * 0.085, y, 0.52), 0.045, GOLD, seg=6)
            cyl("ValveStem", (x, y, 0.64), (x + s * 0.05, y, 0.64), 0.008, CHROME, seg=5, caps=(False, False))
            box("ValveT", (x + s * 0.05, y, 0.64), (0.02, 0.016, 0.07), BLACK, bevel=0.0)
    bbox("Crosslays", (-BW + 0.02, -0.43, BODY_TOP), (BW - 0.02, -0.23, BODY_TOP + 0.12), HOSE, bevel=0.03, seg=2)
    for y in (-0.38, -0.28):
        bbox("CrossStrap", (-BW + 0.01, y - 0.012, BODY_TOP), (BW - 0.01, y + 0.012, BODY_TOP + 0.125), BLACK, bevel=0.0)

    # ---------- body: compartments with roll-up doors, hose bed on top
    B0, B1 = PM1, 1.46
    bprof = [(B0, zb)] + arch(RY, WR, 0.375, zb, 7) + [(B1, zb), (B1, BODY_TOP), (B0, BODY_TOP)]
    prism("BodyBox", bprof, -BW, BW, PAINT, bevel=0.025, seg=2)
    for s in (-1, 1):
        arc_band("RearLip", RY, WR, 0.375, 0.405, s * (BW - 0.01), s * (BW + 0.03), BLACK, a0=0.05, a1=pi - 0.05,
                 steps=7, bevel=0.0)
        x = s * BW
        for (y0, y1, z0, z1) in ((-0.16, 0.37, 0.36, 1.02), (0.44, 1.16, 0.77, 1.02), (1.22, 1.41, 0.36, 1.02)):
            shutter(s, x, y0, y1, z0, z1, ALU)
        for (y0, y1) in ((-0.19, 0.40), (1.20, 1.44)):
            bbox("BodyStripe", (min(x, x + s * 0.006), y0, 0.29), (max(x, x + s * 0.006), y1, 0.33), STRIPE, bevel=0.0)
        bbox("SideStep", (min(s * (BW - 0.04), s * (BW + 0.06)), -0.16, 0.22),
             (max(s * (BW - 0.04), s * (BW + 0.06)), 0.38, 0.26), ALU, bevel=0.0)
        cyl("GrabRail", (x + s * 0.035, -0.19, 0.45), (x + s * 0.035, -0.19, 0.99), 0.012, CHROME, seg=6)
        for z in (0.47, 0.97):
            box("GrabFoot", (x + s * 0.018, -0.19, z), (0.036, 0.02, 0.02), CHROME, bevel=0.0)
        bbox("BedRail", (min(x, x - s * 0.03), 0.50, BODY_TOP), (max(x, x - s * 0.03), 1.46, BODY_TOP + 0.1), ALU,
             bevel=0.0)
    # hose bed: folded yellow hose (scalloped top), aluminium deck in front
    folds, f0, f1 = 8, 0.52, 1.44
    hp = [(f0, BODY_TOP), (f1, BODY_TOP)]
    for k in range(folds):
        yc = f1 - (k + 0.5) * (f1 - f0) / folds
        hw = (f1 - f0) / folds / 2
        hp += [(yc + hw * 0.98, BODY_TOP + 0.06), (yc + hw * 0.55, BODY_TOP + 0.085), (yc, BODY_TOP + 0.093),
               (yc - hw * 0.55, BODY_TOP + 0.085)]
    hp.append((f0, BODY_TOP + 0.06))
    prism("HoseBed", hp, -BW + 0.03, BW - 0.03, HOSE, bevel=0.0, smooth=lambda p: len(p.vertices) == 4)
    bbox("Deck", (-BW + 0.01, -0.21, BODY_TOP), (BW - 0.01, 0.50, BODY_TOP + 0.02), ALU, bevel=0.0)

    # ---------- deck-gun riser (fixed part)
    cyl("Riser", (PIVOT.x, PIVOT.y, BODY_TOP + 0.10), (PIVOT.x, PIVOT.y, PIVOT.z - 0.05), 0.04, CHROME, seg=8,
        caps=(False, False))
    cyl("RiserFlange", (PIVOT.x, PIVOT.y, BODY_TOP + 0.10), (PIVOT.x, PIVOT.y, BODY_TOP + 0.13), 0.07, PAINT, seg=10)
    for s in (-1, 1):
        beam("GunStand", (s * 0.12, PIVOT.y, BODY_TOP + 0.1), (s * 0.03, PIVOT.y, PIVOT.z - 0.12), 0.03, 0.03, BLACK,
             bevel=0.0)

    # ---------- two-section ladder on overhead racks
    LZ = BODY_TOP + 0.20
    for y in (-0.08, 1.30):
        for s in (-1, 1):
            beam("RackPost", (s * 0.3, y, BODY_TOP + 0.02), (s * 0.24, y, LZ - 0.02), 0.035, 0.035, BLACK, bevel=0.0)
        bbox("RackBar", (-0.32, y - 0.025, LZ - 0.035), (0.32, y + 0.025, LZ - 0.015), BLACK, bevel=0.0)
    L0, L1 = -0.15, 1.62
    for s in (-1, 1):
        bbox("LadderRail", (s * 0.22 - 0.02, L0, LZ - 0.015), (s * 0.22 + 0.02, L1, LZ + 0.055), ALU, bevel=0.0)
        bbox("LadderRail2", (s * 0.17 - 0.015, L0 + 0.05, LZ + 0.055), (s * 0.17 + 0.015, L1 - 0.12, LZ + 0.1), ALU,
             bevel=0.0)
    n = 13
    for k in range(n):
        y = L0 + 0.07 + (L1 - L0 - 0.14) * k / (n - 1)
        cyl("Rung", (-0.21, y, LZ + 0.02), (0.21, y, LZ + 0.02), 0.012, ALU, seg=5, caps=(False, False))
    for k in range(8):
        y = L0 + 0.13 + (L1 - L0 - 0.3) * k / 7
        cyl("Rung2", (-0.16, y, LZ + 0.08), (0.16, y, LZ + 0.08), 0.01, ALU, seg=5, caps=(False, False))

    # ---------- rear: tail lights, step, grab handles, centre shutter
    for s in (-1, 1):
        x = s * 0.42
        bbox("TailHousing", (x - 0.07, B1 - 0.01, 0.40), (x + 0.07, B1 + 0.02, 0.78), CHROME, bevel=0.0)
        for z, m in ((0.72, TAILLIGHT), (0.62, AMBER), (0.52, TAILLIGHT)):
            cyl("TailLamp", (x, B1 + 0.02, z), (x, B1 + 0.035, z), 0.04, m, seg=6, caps=(False, True), phase=0)
        bbox("RearStripe", (x - 0.06, B1, 0.83), (x + 0.06, B1 + 0.006, 1.0), STRIPE, bevel=0.0)
        cyl("RearGrab", (s * 0.26, B1 + 0.04, 0.5), (s * 0.26, B1 + 0.04, 0.99), 0.012, CHROME, seg=6)
        for z in (0.52, 0.97):
            box("GrabFoot", (s * 0.26, B1 + 0.02, z), (0.02, 0.04, 0.02), CHROME, bevel=0.0)
        box("MudFlap", (s * RT, RY + 0.42, 0.25), (0.26, 0.015, 0.22), BLACK, bevel=0.0)
    # rear centre shutter: same slatted strip, facing +Y
    prof2 = [Vector((-0.2, B1 - 0.002, 0.38))]
    nrib = 10
    for k in range(nrib):
        z = 0.38 + k * 0.064
        prof2 += [Vector((-0.2, B1 + 0.003, z + 0.002)), Vector((-0.2, B1 + 0.01, z + 0.058))]
    prof2.append(Vector((-0.2, B1 - 0.002, 1.02)))
    strip("RearShutter", prof2, X * 0.4, ALU, Y)
    bbox("RearShutterBar", (-0.17, B1, 0.40), (0.17, B1 + 0.03, 0.425), CHROME, bevel=0.0)
    bbox("TailStep", (-BW, B1 - 0.02, 0.20), (BW, B1 + 0.14, 0.27), ALU, bevel=0.01)

    body = collapse("Body", GROUP)
    weather(body, 12, 11, [(GRIME, 3, (2.0, 3.5)), (RUST, 1, (1.0, 1.6))], {"Paint", "White"}, bottom_bias=2.8,
            sides=("x", "x", "y"), size=(0.018, 0.04))

    # ---------- LightBar (separate, origin at its base centre)
    new_group()
    shaped_box("LBBase", lambda sx, sy, sz: (sx * (0.42 if sz < 0 else 0.4), LB.y + sy * 0.07,
                                             LB.z + (0.012 if sz < 0 else 0.03)), BLACK, bevel=0.01, seg=1)
    for s in (-1, 1):
        box("LBFoot", (s * 0.3, LB.y, LB.z + 0.006), (0.06, 0.1, 0.012), BLACK, bevel=0.0)
    for i in range(6):
        x0 = -0.4 + i * (0.8 / 6)
        m = mat("SirenRed", "ff1a1a", 0.15, emit="ff0d0d", emit_strength=4.0) if i < 3 else \
            mat("SirenBlue", "2a5bff", 0.15, emit="1f4dff", emit_strength=4.0)
        shaped_box("Lens", lambda sx, sy, sz, x0=x0: (x0 + (0.006 if sx < 0 else 0.8 / 6 - 0.006), LB.y + sy * 0.064,
                                                      LB.z + (0.03 if sz < 0 else 0.09)), m, bevel=0.02, seg=1)
    lightbar = collapse("LightBar", GROUP, origin=LB)

    # ---------- Cannon (deck gun) - origin at the swivel pivot, aimed forward + up
    new_group()
    ball("Swivel", PIVOT, 0.055, CHROME, seg=8, rings_=5)
    cyl("Yoke", PIVOT - Z * 0.045, PIVOT - Z * 0.09, 0.065, PAINT, seg=10)
    up = X.cross(AIM).normalized()
    cyl("Barrel", PIVOT + AIM * 0.04, PIVOT + AIM * 0.28, 0.035, PAINT, seg=10, caps=(False, False))
    ring("BarrelBand", PIVOT + AIM * 0.27, AIM, 0.03, 0.045, 0.03, CHROME, seg=10, sides=(0, 1, 3))
    cyl("Tip", PIVOT + AIM * 0.28, PIVOT + AIM * 0.40, 0.04, CHROME, seg=10, r1=0.026, caps=(False, False))
    ring("TipRing", PIVOT + AIM * 0.42, AIM, 0.02, 0.034, 0.04, BLACK, seg=10)
    for s in (-1, 1):
        tube("Handle", [PIVOT + AIM * 0.12 + X * s * 0.03, PIVOT + AIM * 0.04 + X * s * 0.1,
                        PIVOT - AIM * 0.10 + X * s * 0.1 + up * 0.04], 0.011, BLACK, sides=5, rad=0.03, n=1)
    cannon = collapse("Cannon", GROUP, origin=PIVOT)
    nozzle = empty("Nozzle", NOZ, rot=(-math.radians(28), 0, 0))

    wheels = place_wheels([("WheelFL", FT, FY, WR), ("WheelFR", -FT, FY, WR)], R=WR, W=0.22, rim_r=0.18,
                          tread="road", rim_style="truck", rim_paint=ALU, steps=16, rim_steps=12, lugs=6, cap=PAINT)
    wheels += place_wheels([("WheelRL", RT, RY, WR), ("WheelRR", -RT, RY, WR)], R=WR, W=0.28, rim_r=0.18,
                           tread="road", rim_style="truck", rim_paint=ALU, steps=16, rim_steps=12, lugs=6, cap=PAINT)
    steering = build_steering(STEER, STEER_AX, R=0.09)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat, lightbar, cannon, nozzle]
    info = {"wheel_radius": WR, "Cannon pivot godot": godot(PIVOT), "Nozzle godot": godot(NOZ),
            "Nozzle aim godot (+Z local)": godot(AIM)}
    return objs, info, SEAT


def star(n=5, r0=1.0, r1=0.45, rot=pi / 2):
    return [((r0 if k % 2 == 0 else r1) * math.cos(rot + pi * k / n), (r0 if k % 2 == 0 else r1) * math.sin(rot + pi * k / n))
            for k in range(2 * n)]


def build_lightbar(LB, half=0.36, depth=0.075, n=6, lens_h=0.06):
    """Roof light bar: black base, red lenses on the vehicle's left (+X), blue on the right."""
    new_group()
    RED = mat("SirenRed", "ff1a1a", 0.15, emit="ff0d0d", emit_strength=4.0)
    BLUE = mat("SirenBlue", "2a5bff", 0.15, emit="1f4dff", emit_strength=4.0)
    shaped_box("LBBase", lambda sx, sy, sz: (sx * (half + 0.02 if sz < 0 else half), LB.y + sy * depth,
                                             LB.z + (0.012 if sz < 0 else 0.03)), BLACK, bevel=0.0)
    for s in (-1, 1):
        box("LBFoot", (s * half * 0.7, LB.y, LB.z + 0.006), (0.06, depth * 1.4, 0.012), BLACK, bevel=0.0)
    w = 2 * half / n
    for i in range(n):
        x0 = -half + i * w
        m = BLUE if i < n // 2 else RED
        shaped_box("Lens", lambda sx, sy, sz, x0=x0: (x0 + (0.006 if sx < 0 else w - 0.006), LB.y + sy * (depth - 0.006),
                                                      LB.z + (0.03 if sz < 0 else 0.03 + lens_h)), m, bevel=0.018, seg=1)
    return collapse("LightBar", GROUP, origin=LB)


def build_police_car():
    BLK = mat("Paint", "18191c", 0.28, coat=0.8)
    WHT = mat("White", "f2f1ec", 0.3, coat=0.7)
    PRIMER = mat("Primer", "8d9094", 0.8)
    SCRATCH = mat("Scratch", "b9bcc0", 0.5, metal=0.6)
    GOLD = mat("Gold", "e6b33a", 0.25, metal=1.0)
    BLUEM = mat("BadgeBlue", "1d3f8f", 0.35)
    CRACK = mat("Crack", "eef4f8", 0.2)

    WR = 0.27
    FY, RY = -0.78, 0.80
    TR = 0.45
    HW = 0.52
    BELT, ROOF0, ROOF1 = 0.62, 0.95, 1.0
    SEAT = Vector((0.21, 0.06, 0.40))
    STEER = SEAT + Vector((0, -0.29, 0.10))
    STEER_AX = Vector((0, 0.6, 0.8))
    WS0, WS1 = -0.46, -0.15     # windshield base / top y
    RW0, RW1 = 0.70, 0.44      # rear window base / top y
    LB = Vector((0.0, 0.10, ROOF1))
    zb = 0.19

    new_group()
    # ---------- front clip (bonnet + fenders), rear clip (trunk + quarters)
    fprof = [(-1.20, zb + 0.02)] + arch(FY, WR, 0.32, zb, 7) + [(WS0, zb), (WS0, BELT - 0.005), (-1.16, 0.565),
                                                               (-1.25, 0.52), (-1.27, 0.40), (-1.26, 0.27)]
    shoulder_prism("FrontClip", fprof, HW, BLK, inset=0.05, drop=0.035, z_lo=0.45, z_hi=0.56, bevel=0.025, seg=2)
    rprof = [(RW0 - 0.02, zb)] + arch(RY, WR, 0.32, zb, 7) + [(1.22, zb + 0.03), (1.26, 0.28), (1.27, 0.44),
                                                             (1.25, 0.60), (1.18, 0.635), (RW0 - 0.02, BELT + 0.01)]
    shoulder_prism("RearClip", rprof, HW, BLK, inset=0.05, drop=0.035, z_lo=0.47, z_hi=0.6, bevel=0.025, seg=2)
    # ---------- doors (white), sills, floor: an open-topped tub so the driver shows
    for s in (-1, 1):
        dprof = [(WS0 - 0.01, zb + 0.03), (RW0 - 0.01, zb + 0.03), (RW0 - 0.01, BELT), (WS0 - 0.01, BELT)]
        prism("Door", dprof, s * (HW - 0.045), s * HW, WHT, bevel=0.02, seg=1)
        bbox("Sill", (min(s * (HW - 0.03), s * (HW + 0.012)), WS0 + 0.02, zb - 0.01),
             (max(s * (HW - 0.03), s * (HW + 0.012)), RW0 - 0.04, zb + 0.06), BLK, bevel=0.01)
        x = s * HW
        for y in (0.15,):
            beam("DoorSeam", (x + s * 0.002, y, zb + 0.07), (x + s * 0.002, y, BELT - 0.005), 0.004, 0.007, BLACK,
                 side=Y, bevel=0)
        for y in (-0.02, 0.50):
            box("DoorHandle", (x + s * 0.007, y, BELT - 0.06), (0.014, 0.075, 0.02), CHROME, bevel=0.0)
        # door markings: gold star badge on the front door, POLICE on the rear
        o = Vector((x, -0.18, 0.42))
        flat_poly("Badge", star(5, 0.085, 0.04), o, (0, s, 0), Z, GOLD)
        flat_poly("BadgeIn", [(math.cos(2 * pi * k / 10) * 0.028, math.sin(2 * pi * k / 10) * 0.028) for k in range(10)],
                  o, (0, s, 0), Z, BLUEM, lift=0.0045)
        text("Police", "POLICE", 0.095, (x, 0.40, 0.43), (0, s, 0), Z, BLACK, font="Arial Black.ttf", res=1)
        # chrome belt-line trim
        bbox("BeltTrim", (min(x - s * 0.04, x + s * 0.004), WS0, BELT - 0.006), (max(x - s * 0.04, x + s * 0.004), RW0,
                                                                                   BELT + 0.006), CHROME, bevel=0.0)
        arc_band("ArchLipF", FY, WR, 0.32, 0.345, s * (HW - 0.02), s * (HW + 0.012), BLK, a0=0.08, a1=pi - 0.08,
                 steps=7, bevel=0.0)
        arc_band("ArchLipR", RY, WR, 0.32, 0.345, s * (HW - 0.02), s * (HW + 0.012), BLK, a0=0.08, a1=pi - 0.08,
                 steps=7, bevel=0.0)
    bbox("Floor", (-HW + 0.04, WS0, zb), (HW - 0.04, RW0, 0.27), BLACK, bevel=0.0)
    bbox("Tunnel", (-0.07, WS0, 0.26), (0.07, RW0, 0.33), BLACK, bevel=0.015)
    # ---------- greenhouse: white pillars + roof, glass front and back, side windows rolled down
    for s in (-1, 1):
        beam("APillar", (s * (HW - 0.035), WS0 + 0.01, BELT), (s * (HW - 0.075), WS1, ROOF0), 0.05, 0.05, WHT,
             bevel=0.012)
        beam("BPillar", (s * (HW - 0.045), 0.17, BELT), (s * (HW - 0.07), 0.17, ROOF0), 0.06, 0.05, WHT, bevel=0.0)
        shaped_box("CPillar", lambda sx, sy, sz, s=s: (s * (HW - (0.03 if sz < 0 else 0.07)) - s * (0.0 if sx * s > 0 else 0.05),
                                                       (RW0 - 0.05 if sz < 0 else RW1 - 0.08) if sy < 0 else
                                                       (RW0 + 0.0 if sz < 0 else RW1),
                                                       BELT if sz < 0 else ROOF0), WHT, bevel=0.01, seg=1)
    shaped_box("Roof", lambda sx, sy, sz: (sx * (HW - (0.06 if sz < 0 else 0.08)), (WS1 - 0.02 if sz > 0 else WS1 - 0.03)
               if sy < 0 else RW1 + 0.02, ROOF0 - 0.01 if sz < 0 else ROOF1), WHT, bevel=0.03, seg=2)
    for pts, nm in (([(-HW + 0.06, WS0 + 0.02, BELT + 0.005), (HW - 0.06, WS0 + 0.02, BELT + 0.005),
                      (HW - 0.09, WS1 - 0.01, ROOF0 - 0.01), (-HW + 0.09, WS1 - 0.01, ROOF0 - 0.01)], "Windshield"),
                    ([(-HW + 0.08, RW0 - 0.03, BELT + 0.01), (HW - 0.08, RW0 - 0.03, BELT + 0.01),
                      (HW - 0.1, RW1 + 0.01, ROOF0 - 0.01), (-HW + 0.1, RW1 + 0.01, ROOF0 - 0.01)], "RearWindow")):
        bm = bmesh.new()
        bm.faces.new([bm.verts.new(p) for p in pts])
        finish_obj(nm, bm, WINDOW, smooth=False)
    # crack in the windshield (passenger side)
    wsn = (Vector((0, WS1 - WS0, ROOF0 - BELT))).normalized()
    c0 = Vector((-0.22, WS0 + (WS1 - WS0) * 0.45, BELT + (ROOF0 - BELT) * 0.45)) - wsn.cross(X) * 0.0
    for a, ln in ((0.3, 0.12), (1.9, 0.09), (3.6, 0.1), (4.9, 0.07)):
        d = X * math.cos(a) + wsn * math.sin(a)
        beam("Crack", c0, c0 + d * ln, 0.004, 0.002, CRACK, side=X.cross(wsn), bevel=0.0)
    # ---------- interior: dash, seats, cage partition, rear bench
    bbox("Dash", (-HW + 0.05, WS0 - 0.02, 0.44), (HW - 0.05, WS0 + 0.12, BELT + 0.03), BLACK, bevel=0.02)
    bbox("Laptop", (-0.08, WS0 + 0.12, 0.46), (0.06, WS0 + 0.22, 0.48), METAL, bevel=0.0, )
    beam("LaptopLid", (-0.08, WS0 + 0.2, 0.48), (0.06, WS0 + 0.2, 0.48), 0.12, 0.012, BLACK, side=Vector((0, -0.3, 1)),
         bevel=0.0)
    for x in (SEAT.x, -SEAT.x):
        seat_block(Vector((x, SEAT.y, SEAT.z)), 0.3, 0.28, SEATM, back_h=0.34, tilt=-10, base_h=SEAT.z - 0.07 - 0.27,
                   base_m=BLACK, bolster=False)
    for x in (-0.3, -0.15, 0.0, 0.15, 0.3):
        cyl("CageBar", (x, 0.3, BELT - 0.08), (x, 0.3, ROOF0 - 0.01), 0.008, METAL, seg=4, caps=(False, False))
    bbox("CageFrame", (-HW + 0.06, 0.29, BELT - 0.1), (HW - 0.06, 0.31, BELT - 0.06), METAL, bevel=0.0)
    bbox("RearBench", (-HW + 0.06, 0.36, 0.27), (HW - 0.06, 0.62, 0.38), SEATM, bevel=0.02)
    bbox("RearBack", (-HW + 0.06, 0.58, 0.38), (HW - 0.06, 0.66, 0.6), SEATM, bevel=0.02)
    col_end = STEER - STEER_AX * 0.03
    cyl("Column", col_end - STEER_AX * 0.22, col_end, 0.018, BLACK, seg=6, caps=(False, True))
    # A-pillar spotlight (driver side)
    sp = Vector((HW - 0.01, WS0 + 0.06, BELT + 0.06))
    cyl("SpotStem", sp, sp + X * 0.05, 0.01, CHROME, seg=5, caps=(False, False))
    cyl("Spotlight", sp + X * 0.05 + Y * 0.04, sp + X * 0.05 - Y * 0.06, 0.035, CHROME, seg=10, r1=0.042)
    disc("SpotLens", sp + X * 0.05 - Y * 0.062, -Y, 0.036, HEADLIGHT, seg=10)
    # mirrors
    for s in (-1, 1):
        beam("MirrorArm", (s * (HW - 0.02), WS0 + 0.05, BELT + 0.03), (s * (HW + 0.06), WS0 + 0.05, BELT + 0.06), 0.015,
             0.015, BLK, side=Y, bevel=0.0)
        box("Mirror", (s * (HW + 0.07), WS0 + 0.05, BELT + 0.07), (0.07, 0.03, 0.05), BLK, bevel=0.01)
    # ---------- nose: grille, headlights (one cracked), push bar, bumper
    ny = -1.27
    bbox("Grille", (-0.24, ny - 0.008, 0.33), (0.24, ny + 0.03, 0.48), BLACK, bevel=0.012)
    bbox("GrilleRim", (-0.25, ny - 0.012, 0.47), (0.25, ny + 0.02, 0.49), CHROME, bevel=0.0)
    for i in range(4):
        z = 0.35 + i * 0.033
        bbox("GrilleBar", (-0.23, ny - 0.016, z), (0.23, ny - 0.006, z + 0.008), METAL, bevel=0.0)
    for s in (-1, 1):
        bbox("LampBezel", (s * 0.27 if s > 0 else -0.46, ny - 0.006, 0.36), (0.46 if s > 0 else -0.27, ny + 0.03, 0.47),
             CHROME, bevel=0.008)
        bbox("Headlamp", (s * 0.285 if s > 0 else -0.445, ny - 0.012, 0.372), (0.445 if s > 0 else -0.285, ny, 0.458),
             HEADLIGHT, bevel=0.0)
        box("Indicator", (s * 0.40, ny + 0.01, 0.32), (0.12, 0.03, 0.03), AMBER, bevel=0.0)
    # cracked right lamp: dark fracture lines over the lens
    for a in (0.5, 2.2, 3.9):
        c = Vector((-0.36, ny - 0.014, 0.415))
        beam("LampCrack", c, c + Vector((math.cos(a) * 0.06, 0, math.sin(a) * 0.035)), 0.004, 0.002, BLACK, side=Y, bevel=0)
    # bumper: knocked a few degrees crooked
    box("FrontBumper", (0.0, ny - 0.03, 0.27), (1.02, 0.08, 0.09), CHROME, bevel=0.025, seg=2, rot=(0, -3, 2))
    box("BumperStrip", (0.0, ny - 0.072, 0.268), (0.9, 0.012, 0.03), BLACK, bevel=0.0, rot=(0, -3, 2))
    # push bar
    for s in (-1, 1):
        beam("PushUpright", (s * 0.2, ny - 0.08, 0.22), (s * 0.2, ny - 0.10, 0.6), 0.05, 0.04, BLACK, side=X, bevel=0.008)
        box("PushPad", (s * 0.2, ny - 0.125, 0.42), (0.065, 0.02, 0.24), RUBBER, bevel=0.006)
    for z in (0.34, 0.52):
        beam("PushBar", (-0.24, ny - 0.1, z), (0.24, ny - 0.1, z), 0.035, 0.035, BLACK, side=Z, bevel=0.006)
    for s in (-1, 1):
        cyl("PushLight", (s * 0.12, ny - 0.11, 0.52), (s * 0.12, ny - 0.13, 0.52), 0.022, TAILLIGHT if s > 0 else
            mat("FlashBlue", "3a66ff", 0.15, emit="2a55ff", emit_strength=2.0), seg=8)
    # ---------- tail
    ty = 1.27
    for s in (-1, 1):
        bbox("TailLamp", (s * 0.28 if s > 0 else -0.48, ty - 0.02, 0.42), (0.48 if s > 0 else -0.28, ty + 0.012, 0.55),
             TAILLIGHT, bevel=0.008)
        bbox("Reverse", (s * 0.22 if s > 0 else -0.27, ty - 0.02, 0.44), (0.27 if s > 0 else -0.22, ty + 0.01, 0.53),
             HEADLIGHT, bevel=0.0)
    box("RearBumper", (0.0, ty + 0.03, 0.28), (1.02, 0.07, 0.09), CHROME, bevel=0.025, seg=2)
    bbox("Plate", (-0.11, ty - 0.005, 0.31), (0.11, ty + 0.012, 0.39), mat("Plate", "f0eadc", 0.4), bevel=0.0)
    text("PlateText", "PD-07", 0.04, (0, ty + 0.012, 0.35), (-1, 0, 0), Z, BLACK, font="Arial Black.ttf", res=1)
    cyl("Antenna", (-0.3, 1.0, 0.63), (-0.33, 1.06, 1.05), 0.004, BLACK, seg=4, caps=(False, False))
    for s in (-1, 1):
        cyl("Exhaust", (s * 0.32, 1.1, 0.17), (s * 0.32, 1.30, 0.17), 0.02, METAL, seg=6)
    # chassis glimpses
    cyl("AxleF", (-TR, FY, WR), (TR, FY, WR), 0.035, BLACK, seg=6, caps=(False, False))
    cyl("AxleR", (-TR, RY, WR), (TR, RY, WR), 0.045, BLACK, seg=6, caps=(False, False))

    body = collapse("Body", GROUP)
    # battered: primer-grey repair on the left rear quarter, scuffs, scratches, rust, road grime
    project_patches(body, [((1.2, 1.13, 0.5), (-1, 0, 0), 0.065, 1.6, 0.3, PRIMER),
                           ((-1.2, -1.1, 0.48), (1, 0, 0), 0.06, 1.4, 0.2, PRIMER),
                           ((0.3, -0.8, 1.4), (0, 0, -1), 0.05, 1.6, 0.6, PRIMER)], seed=5)
    weather(body, 10, 21, [(SCRATCH, 2, (5.0, 8.0))], {"Paint", "White"}, bottom_bias=1.0, sides=("x", "x", "y"),
            size=(0.008, 0.012))
    weather(body, 14, 22, [(RUST, 2, (1.0, 1.7)), (GRIME, 3, (2.0, 3.5))], {"Paint", "White", "Primer"},
            bottom_bias=2.5, sides=("x", "x", "y", "z"), size=(0.015, 0.035))

    lightbar = build_lightbar(LB, half=0.36, depth=0.07)
    STEEL = mat("SteelWheel", "34373c", 0.38, metal=0.7)
    wk = dict(R=WR, W=0.2, rim_r=0.16, tread="road", rim_paint=STEEL, steps=16, rim_steps=12, lugs=5, grooves=2)
    wheels = place_wheels([("WheelFL", TR, FY, WR), ("WheelFR", -TR, FY, WR), ("WheelRR", -TR, RY, WR)],
                          rim_style="dog", **wk)
    wheels += place_wheels([("WheelRL", TR, RY, WR)], rim_style="steel", **wk)  # lost its hubcap
    steering = build_steering(STEER, STEER_AX, R=0.075)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat, lightbar]
    return objs, {"wheel_radius": WR, "LightBar godot": godot(LB)}, SEAT


def chevrons(y, x0, x1, z0, z1, n, yel, blk, facing=1):
    """Yellow/black hazard chevrons on a rear face at y (facing +Y)."""
    bbox("HazardBase", (x0, y - 0.003, z0), (x1, y + 0.004, z1), yel, bevel=0.0)
    w = (x1 - x0) / n
    h = z1 - z0
    for k in range(n):
        xa = x0 + k * w
        pts = [(xa + w * 0.25, z0), (xa + w * 0.75, z0), (xa + w * 0.25 + w * 0.5 * 0.0 + w * 0.5, z1),
               (xa + w * 0.25, z1)]
        pts = [(xa, z0), (xa + w * 0.5, z0), (xa + w, z1), (xa + w * 0.5, z1)]
        pts = [(max(x0, min(x1, px)), pz) for px, pz in pts]
        flat_poly("Hazard", [(-px, pz) for px, pz in pts], (0, y, 0), (-1, 0, 0), Z, blk, lift=0.006)


def build_garbage_truck():
    PAINT = mat("Paint", "2f8a3e", 0.32, coat=0.6)
    DARK = mat("PaintDark", "1f5f2b", 0.4, coat=0.4)
    WHITE = mat("White", "f1f0ea", 0.35, coat=0.5)
    STEEL = mat("Steel", "7d8389", 0.45, metal=0.8)
    YEL = mat("Hazard", "f2c21b", 0.4)
    BAG = mat("TrashBag", "202326", 0.3, coat=0.4)
    BAG2 = mat("TrashBagBlue", "2b4f8f", 0.3, coat=0.4)

    WR = 0.30
    FY, MY, RY = -1.00, 0.10, 0.78
    TR = 0.43
    CF, CR = -1.45, -0.56
    HW = 0.53
    BW = 0.53
    BELT, ROOF0, ROOF1 = 0.88, 1.28, 1.34
    FLOOR = 0.64
    SEAT = Vector((0.24, -0.86, 0.74))
    STEER = SEAT + Vector((0, -0.29, 0.10))
    STEER_AX = Vector((0, 0.5, 0.866))
    B0, B1 = -0.52, 1.16
    BT = 1.34                 # packer body top
    zb = 0.27

    new_group()
    # ---------- chassis
    for s in (-1, 1):
        bbox("Rail", (s * 0.34, -1.40, 0.18), (s * 0.24, 1.40, 0.30), BLACK, bevel=0.0)
    for y, r in ((FY, 0.045), (MY, 0.06), (RY, 0.06)):
        cyl("Axle", (-TR, y, WR), (TR, y, WR), r, BLACK, seg=6, caps=(False, False))
    cyl("FuelTank", (0.37, -0.50, 0.30), (0.37, -0.05, 0.30), 0.1, ALU, seg=10)
    cyl("AirTank", (-0.37, -0.50, 0.30), (-0.37, -0.10, 0.30), 0.07, BLACK, seg=8)

    # ---------- cab (cab-over, hollow, open side windows)
    prof = [(CF, zb)] + arch(FY, WR, 0.365, zb, 7) + [(CR, zb), (CR, BELT), (CF + 0.01, BELT)]
    for s in (-1, 1):
        prism("CabSide", prof, s * (HW - 0.05), s * HW, PAINT, bevel=0.02, seg=1)
        arc_band("FenderLip", FY, WR, 0.365, 0.395, s * (HW - 0.01), s * (HW + 0.03), BLACK, a0=0.05, a1=pi - 0.05,
                 steps=7, bevel=0.0)
        box("DoorHandle", (s * (HW + 0.008), -0.66, BELT - 0.05), (0.016, 0.08, 0.02), CHROME, bevel=0.0)
        bbox("CabStep", (min(s * (HW - 0.06), s * (HW + 0.03)), -0.63, 0.22), (max(s * (HW - 0.06), s * (HW + 0.03)),
                                                                              -0.56, 0.26), STEEL, bevel=0.0)
        bbox("CabStripe", (min(s * HW, s * (HW + 0.005)), CF + 0.02, 0.70), (max(s * HW, s * (HW + 0.005)), CR, 0.76),
             WHITE, bevel=0.0)
    bbox("CabFront", (-HW, CF, zb), (HW, CF + 0.06, BELT), PAINT, bevel=0.03, seg=2)
    bbox("CabFloor", (-HW + 0.04, CF + 0.05, FLOOR - 0.04), (HW - 0.04, CR, FLOOR), BLACK, bevel=0.0)
    bbox("CabBack", (-HW, CR - 0.05, zb), (HW, CR, ROOF0 + 0.01), PAINT, bevel=0.02)
    bbox("Dash", (-HW + 0.05, CF + 0.05, BELT - 0.14), (HW - 0.05, CF + 0.17, BELT + 0.02), BLACK, bevel=0.02)
    bbox("Doghouse", (-0.1, CF + 0.15, FLOOR - 0.01), (0.1, -0.82, FLOOR + 0.12), DARK, bevel=0.02)
    wb, wt = CF + 0.02, CF + 0.08
    for s in (-1, 1):
        beam("APillar", (s * (HW - 0.03), wb, BELT), (s * (HW - 0.03), wt, ROOF0), 0.06, 0.06, PAINT, bevel=0.012)
        beam("BPillar", (s * (HW - 0.03), CR - 0.03, BELT), (s * (HW - 0.03), CR - 0.03, ROOF0), 0.06, 0.06, PAINT,
             bevel=0.0)
        tube("MirrorArm", [(s * (HW - 0.01), wb + 0.02, BELT + 0.04), (s * (HW + 0.1), wb - 0.02, BELT + 0.04),
                           (s * (HW + 0.1), wb - 0.02, BELT + 0.3)], 0.01, STEEL, sides=4, rad=0.0)
        box("Mirror", (s * (HW + 0.11), wb - 0.03, BELT + 0.17), (0.03, 0.08, 0.2), BLACK, bevel=0.0)
        box("MirrorGlass", (s * (HW + 0.11), wb - 0.05, BELT + 0.17), (0.022, 0.012, 0.18), CHROME, bevel=0.0)
    glass = [(-HW + 0.05, wb + 0.01, BELT + 0.02), (HW - 0.05, wb + 0.01, BELT + 0.02),
             (HW - 0.05, wt + 0.01, ROOF0 - 0.02), (-HW + 0.05, wt + 0.01, ROOF0 - 0.02)]
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(p) for p in glass])
    finish_obj("Windshield", bm, WINDOW, smooth=False)
    beam("Cowl", (-HW + 0.03, wb, BELT), (HW - 0.03, wb, BELT), 0.05, 0.05, BLACK, side=Z, bevel=0.0)
    beam("Wiper", (0.05, wb - 0.005, BELT + 0.04), (0.3, wb + 0.01, BELT + 0.2), 0.012, 0.01, BLACK, side=X, bevel=0.0)
    shaped_box("Roof", lambda sx, sy, sz: (sx * (HW + 0.01), (CF + 0.04 if sz > 0 else CF + 0.06) if sy < 0
               else CR + 0.01, ROOF0 if sz < 0 else ROOF1), WHITE, bevel=0.035, seg=3)
    # amber beacons
    for s in (-1, 1):
        cyl("BeaconBase", (s * 0.36, CR - 0.12, ROOF1), (s * 0.36, CR - 0.12, ROOF1 + 0.025), 0.05, BLACK, seg=8)
        cyl("Beacon", (s * 0.36, CR - 0.12, ROOF1 + 0.025), (s * 0.36, CR - 0.12, ROOF1 + 0.1), 0.045, AMBER, seg=8,
            r1=0.035)
    # interior
    for x in (SEAT.x, -SEAT.x):
        seat_block(Vector((x, SEAT.y, SEAT.z)), 0.28, 0.26, SEATM, back_h=0.36, tilt=-6, base_h=SEAT.z - 0.07 - FLOOR,
                   base_m=BLACK, bolster=False)
    col_end = STEER - STEER_AX * 0.03
    cyl("Column", col_end - STEER_AX * 0.3, col_end, 0.02, BLACK, seg=6, caps=(False, True))
    # front: black grille band, headlights, heavy steel bumper
    gy = CF - 0.004
    bbox("GrillePanel", (-0.36, gy - 0.02, 0.40), (0.36, gy + 0.01, 0.74), BLACK, bevel=0.012)
    for i in range(5):
        z = 0.44 + i * 0.06
        bbox("GrilleSlot", (-0.32, gy - 0.03, z), (0.32, gy - 0.02, z + 0.022), DARK, bevel=0.0)
    for s in (-1, 1):
        x = s * 0.44
        bbox("LampHousing", (x - 0.07, gy - 0.02, 0.40), (x + 0.07, gy + 0.01, 0.62), BLACK, bevel=0.0)
        bbox("Headlamp", (x - 0.055, gy - 0.026, 0.47), (x + 0.055, gy - 0.016, 0.60), HEADLIGHT, bevel=0.0)
        bbox("Indicator", (x - 0.055, gy - 0.026, 0.42), (x + 0.055, gy - 0.016, 0.455), AMBER, bevel=0.0)
        box("TowHook", (s * 0.2, CF - 0.14, 0.24), (0.04, 0.05, 0.06), YEL, bevel=0.0)
    shaped_box("Bumper", lambda sx, sy, sz: (sx * (0.56 if sy > 0 else 0.54), CF - (0.12 if sy < 0 else 0.0),
                                             0.19 if sz < 0 else 0.36), STEEL, bevel=0.025, seg=1)
    # exhaust stack behind the cab
    cyl("Stack", (-0.42, CR + 0.04, 0.5), (-0.42, CR + 0.04, 1.52), 0.035, CHROME, seg=8)
    cyl("StackGuard", (-0.42, CR + 0.04, 0.9), (-0.42, CR + 0.04, 1.2), 0.05, METAL, seg=8)

    # ---------- packer body: rounded box with vertical ribs
    # the two arches overlap between the tandem axles: merge them into one long cut-out
    a1 = arch(MY, WR, 0.375, zb, 6)
    a2 = arch(RY, WR, 0.375, zb, 6)
    bridge_z = WR + 0.375 * 0.92
    cut = [p for p in a1 if p[0] <= MY] + [(MY + 0.12, bridge_z), (RY - 0.12, bridge_z)] + [p for p in a2 if p[0] >= RY]
    bprof = [(B0, zb)] + cut + [(B1, zb), (B1, BT), (B0, BT)]
    shoulder_prism("Packer", bprof, BW, PAINT, inset=0.07, drop=0.07, z_lo=1.0, z_hi=BT, bevel=0.03, seg=2)
    for s in (-1, 1):
        x = s * BW
        for y in (-0.47, 0.44, B1 - 0.035):
            bbox("Rib", (min(x - s * 0.01, x + s * 0.03), y - 0.03, 0.35 if y < -0.2 else 0.7),
                 (max(x - s * 0.01, x + s * 0.03), y + 0.03, BT - 0.08), DARK, bevel=0.0)
        bbox("BodySill", (min(x - s * 0.02, x + s * 0.035), B0, zb - 0.02), (max(x - s * 0.02, x + s * 0.035), MY - 0.39,
                                                                            zb + 0.06), DARK, bevel=0.0)
        arc_band("ArchLip", MY, WR, 0.375, 0.405, s * (BW - 0.01), s * (BW + 0.03), BLACK, a0=0.35, a1=pi - 0.05,
                 steps=5, bevel=0.0)
        arc_band("ArchLip", RY, WR, 0.375, 0.405, s * (BW - 0.01), s * (BW + 0.03), BLACK, a0=0.05, a1=pi - 0.35,
                 steps=5, bevel=0.0)
        bbox("ArchTop", (min(s * (BW - 0.01), s * (BW + 0.03)), MY + 0.12, bridge_z), (max(s * (BW - 0.01),
                                                                                         s * (BW + 0.03)), RY - 0.12,
                                                                                     bridge_z + 0.03), BLACK, bevel=0.0)
        text("Logo", "CITY WASTE", 0.105, (x, -0.02, 1.0), (0, s, 0), Z, WHITE, font="Arial Black.ttf", res=1)
        bbox("BodyStripe", (min(x, x + s * 0.005), B0 + 0.02, 0.70), (max(x, x + s * 0.005), B1 - 0.02, 0.76), WHITE,
             bevel=0.0)
        bbox("SideLamp", (min(x, x + s * 0.01), -0.3, 0.40), (max(x, x + s * 0.01), -0.24, 0.43), AMBER, bevel=0.0)
    # roof rails on the packer
    for s in (-1, 1):
        bbox("RoofRail", (s * 0.30 - 0.025, B0 + 0.05, BT - 0.005), (s * 0.30 + 0.025, B1 - 0.05, BT + 0.03), DARK,
             bevel=0.0)

    # ---------- tailgate + hopper (side plates full, centre notched for the loading mouth)
    T0, T1 = B1, 1.58

    def ty(f):
        return T0 + f * (T1 - T0)
    tg = [(T0, 0.30), (ty(0.58), 0.30), (ty(0.92), 0.40), (T1, 0.56), (T1 - 0.02, 0.62), (T1 + 0.02, 1.0),
          (ty(0.81), 1.22), (ty(0.35), 1.40), (T0, 1.40)]
    for s in (-1, 1):
        prism("TailgateSide", tg, s * (BW - 0.06), s * (BW + 0.01), PAINT, bevel=0.025, seg=1)
        # tailgate lift cylinder: black barrel on the body, chrome rod up to the tailgate
        cyl("LiftCyl", (s * (BW + 0.04), T0 - 0.09, 0.62), (s * (BW + 0.04), T0 - 0.03, 1.0), 0.03, BLACK, seg=6)
        cyl("LiftRod", (s * (BW + 0.04), T0 - 0.035, 0.98), (s * (BW + 0.04), T0 + 0.02, 1.26), 0.014, CHROME, seg=6,
            caps=(False, False))
        for (y, z) in ((T0 - 0.09, 0.62), (T0 + 0.02, 1.26)):
            box("Clevis", (s * (BW + 0.025), y, z), (0.05, 0.05, 0.05), STEEL, bevel=0.0)
        # rear riding step + grab handle for the crew
        bbox("RideStep", (min(s * 0.32, s * 0.54), T1 - 0.05, 0.30), (max(s * 0.32, s * 0.54), T1 + 0.12, 0.34), STEEL,
             bevel=0.0)
        cyl("RideGrab", (s * 0.46, T1 + 0.05, 0.62), (s * 0.46, T1 + 0.05, 1.05), 0.012, CHROME, seg=6)
        for z in (0.64, 1.03):
            box("GrabFoot", (s * 0.46, T1 + 0.02, z), (0.02, 0.05, 0.02), CHROME, bevel=0.0)
        # tail lights in the corner posts
        bbox("TailLamp", (min(s * 0.40, s * 0.50), T1 + 0.015, 0.44), (max(s * 0.40, s * 0.50), T1 + 0.03, 0.52),
             TAILLIGHT, bevel=0.0)
        bbox("TailAmber", (min(s * 0.40, s * 0.50), T1 + 0.015, 0.36), (max(s * 0.40, s * 0.50), T1 + 0.03, 0.43),
             AMBER, bevel=0.0)
        cyl("TopLamp", (s * 0.42, ty(0.52), 1.30), (s * 0.42, ty(0.6), 1.33), 0.03, AMBER, seg=6)
    cw = BW - 0.06
    tgc = [(T0, 0.30), (ty(0.58), 0.30), (ty(0.92), 0.40), (T1, 0.56), (T1 - 0.02, 0.62), (ty(0.38), 0.66),
           (ty(0.27), 0.84), (ty(0.54), 1.0), (T1 + 0.02, 1.0), (ty(0.81), 1.22), (ty(0.35), 1.40), (T0, 1.40)]
    prism("TailgateCentre", tgc, -cw, cw, PAINT, bevel=0.02, seg=1)
    # dark hopper interior: floor, back wall (packer blade), roof
    bm = bmesh.new()
    pts = [(T1 - 0.03, 0.625), (ty(0.38), 0.665), (ty(0.27), 0.84), (ty(0.54), 0.995), (T1 - 0.01, 0.995)]
    strip("Hopper", [Vector((-cw + 0.002, y, z)) for y, z in pts], X * (2 * cw - 0.004), BLACK, Vector((0, 1, 0.3)))
    bbox("Blade", (-cw + 0.02, ty(0.33), 0.74), (cw - 0.02, ty(0.4), 0.9), STEEL, bevel=0.0)
    # hopper sill (steel lip) + hazard chevrons on the lower rear
    bbox("Sill", (-BW, T1 - 0.04, 0.55), (BW, T1 + 0.03, 0.63), STEEL, bevel=0.01)
    chevrons(T1 + 0.012, -0.38, 0.38, 0.38, 0.52, 8, YEL, BLACK)
    # a couple of trash bags poking out of the hopper
    ball("Bag", (-0.18, T1 - 0.13, 0.74), 0.12, BAG, seg=8, rings_=5, squash=0.8)
    ball("Bag", (0.12, T1 - 0.15, 0.74), 0.11, BAG2, seg=8, rings_=5, squash=0.85)
    cyl("BagTie", (-0.18, T1 - 0.05, 0.8), (-0.2, T1 - 0.01, 0.85), 0.02, BAG, seg=5, r1=0.005)
    for s in (-1, 1):
        box("MudFlap", (s * TR, RY + 0.4, 0.25), (0.26, 0.015, 0.22), BLACK, bevel=0.0)

    body = collapse("Body", GROUP)
    weather(body, 16, 31, [(GRIME, 3, (2.0, 3.5)), (RUST, 2, (1.0, 1.6))], {"Paint", "PaintDark", "White"},
            bottom_bias=3.0, sides=("x", "x", "y"), size=(0.02, 0.045))

    wk = dict(R=WR, W=0.24, rim_r=0.18, tread="road", rim_style="truck", rim_paint=WHITE, steps=16, rim_steps=12,
              lugs=6, cap=STEEL, grooves=1)
    wheels = place_wheels([("WheelFL", TR, FY, WR), ("WheelFR", -TR, FY, WR), ("WheelML", TR, MY, WR),
                           ("WheelMR", -TR, MY, WR), ("WheelRL", TR, RY, WR), ("WheelRR", -TR, RY, WR)], **wk)
    steering = build_steering(STEER, STEER_AX, R=0.09)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat]
    return objs, {"wheel_radius": WR}, SEAT


TOPS = (0.62, 0.36, 0.1, -0.1, -0.36, -0.62)


def striped(k, span):
    """Face material for TOPS-lofted sections: 0 paint, 1 stripe, 2 pinstripe."""
    return {3: 1, 7: 1, 5: 2}.get(k, 0)


def roundel(num, origin, right, up, r, disc_m, txt_m, lift=0.004):
    flat_poly("Roundel", [(math.cos(2 * pi * k / 16) * r, math.sin(2 * pi * k / 16) * r) for k in range(16)], origin,
              right, up, disc_m, lift=lift)
    text("Number", num, r * 1.25, origin, right, up, txt_m, font="Arial Black.ttf", lift=lift + 0.002, res=1)


def build_race_car():
    PAINT = mat("Paint", "ffbf00", 0.3, coat=0.45)
    STRIPE = mat("Stripe", "16171a", 0.3, coat=0.6)
    ACCENT = mat("Accent", "e5262b", 0.3, coat=0.8)
    WHITE = mat("White", "f6f5f0", 0.35, coat=0.5)
    CARBON = mat("Carbon", "222326", 0.35, coat=0.4)
    MARK = mat("TyreMark", "f2f2f2", 0.6)

    WR = 0.25
    FY, RY = -0.74, 0.64
    FT, RT = 0.47, 0.50
    SEAT = Vector((0.0, -0.04, 0.23))
    STEER = SEAT + Vector((0, -0.27, 0.12))
    STEER_AX = Vector((0, 0.8, 0.6))

    new_group()
    # ---------- nose cone with twin stripes
    nose = [(-1.20, 0.19, 0.055, 0.04), (-1.05, 0.21, 0.10, 0.065), (-0.74, 0.245, 0.155, 0.10),
            (-0.42, 0.26, 0.205, 0.14)]
    secs = [section(y, rrect(0, cz, hw, hh, min(hw, hh) * 0.7, n=2, top=TOPS)) for y, cz, hw, hh in nose]
    loft("Nose", secs, [PAINT, STRIPE, ACCENT], bevel=0.0, smooth=True, face_mat=striped)
    # ---------- cockpit: side walls, floor, black coaming pad
    def tub(hw, z0, z1, wall=0.045, r=0.07):
        """U-shaped cockpit tub cross-section: rounded outside, open top."""
        return ([(hw - wall, z1), (hw - 0.012, z1), (hw, z1 - 0.012)] + quarter(hw, z0, r, 1) + quarter(hw, z0, r, -1) +
                [(-hw, z1 - 0.012), (-hw + 0.012, z1), (-hw + wall, z1), (-hw + wall, z0 + 0.04), (hw - wall, z0 + 0.04)])

    def quarter(hw, z0, r, side):
        c = (side * (hw - r), z0 + r)
        a0, a1 = (0, -pi / 2) if side > 0 else (-pi / 2, -pi)
        return [(c[0] + math.cos(a0 + (a1 - a0) * k / 2) * r, c[1] + math.sin(a0 + (a1 - a0) * k / 2) * r)
                for k in range(3)]
    loft("Tub", [section(-0.43, tub(0.205, 0.12, 0.40)), section(0.28, tub(0.25, 0.11, 0.42))], PAINT, bevel=0.0,
         smooth=lambda p: len(p.vertices) == 4)
    bbox("CockpitFloor", (-0.21, -0.43, 0.11), (0.21, 0.28, 0.15), CARBON, bevel=0.0)
    tube("Coaming", [(0.0, -0.40, 0.405), (0.2, -0.40, 0.405), (0.2, 0.25, 0.405), (-0.2, 0.25, 0.405),
                     (-0.2, -0.40, 0.405), (0.001, -0.40, 0.405)], 0.022, BLACK, sides=5, rad=0.08, n=2)
    seat_block(SEAT, 0.3, 0.26, SEATM, back_h=0.26, tilt=-18, bolster=False)
    for s in (-1, 1):  # red speed stripe along the tub flank
        rgt = Vector((s * 0.045, s * 0.71, 0)).normalized()
        flat_poly("SideStripe", [(-0.36, -0.02), (0.30, -0.02), (0.34, 0.02), (-0.32, 0.02)],
                  (s * 0.2275, -0.075, 0.33), rgt, Z, ACCENT, lift=0.004)
        flat_poly("SideStripe2", [(-0.30, -0.008), (0.24, -0.008), (0.26, 0.008), (-0.28, 0.008)],
                  (s * 0.2275, -0.075, 0.285), rgt, Z, STRIPE, lift=0.004)
    col_end = STEER - STEER_AX * 0.02
    cyl("Column", col_end - STEER_AX * 0.16, col_end, 0.015, BLACK, seg=5, caps=(False, True))
    bbox("Dash", (-0.18, -0.44, 0.30), (0.18, -0.38, 0.40), CARBON, bevel=0.01)
    # ---------- engine cover + airbox/roll hoop (above the helmet) + sidepods
    eng = [(0.26, 0.27, 0.25, 0.16), (0.55, 0.27, 0.215, 0.15), (0.86, 0.245, 0.135, 0.11), (1.05, 0.22, 0.075, 0.07)]
    secs = [section(y, rrect(0, cz, hw, hh, min(hw, hh) * 0.7, n=2, top=TOPS)) for y, cz, hw, hh in eng]
    loft("EngineCover", secs, [PAINT, STRIPE, ACCENT], bevel=0.0, smooth=True, face_mat=striped)
    air = [(0.27, 0.60, 0.065, 0.19), (0.38, 0.59, 0.075, 0.18), (0.62, 0.50, 0.07, 0.09), (0.84, 0.43, 0.045, 0.03)]
    secs = [section(y, rrect(0, cz, hw, hh, min(hw, hh) * 0.8, n=2)) for y, cz, hw, hh in air]
    loft("Airbox", secs, PAINT, bevel=0.0, smooth=True)
    flat_poly("Intake", [(x, z) for x, z in rrect(0, 0.68, 0.048, 0.075, 0.04, n=2)], (0, 0.269, 0), (-1, 0, 0), Z,
              BLACK, lift=0.0)
    tube("RollHoop", [(0.17, 0.27, 0.40), (0.10, 0.30, 0.83), (-0.10, 0.30, 0.83), (-0.17, 0.27, 0.40)], 0.018,
         CHROME, sides=6, rad=0.06, n=2)
    for s in (-1, 1):
        pods = [(-0.16, s * 0.35, 0.215, 0.105, 0.095), (0.12, s * 0.355, 0.215, 0.115, 0.1),
                (0.36, s * 0.31, 0.2, 0.085, 0.08), (0.56, s * 0.25, 0.18, 0.045, 0.05)]
        secs = [section(y, rrect(cx, cz, hw, hh, min(hw, hh) * 0.75, n=2)) for y, cx, cz, hw, hh in pods]
        loft("Sidepod", secs, PAINT, bevel=0.0, smooth=True)
        flat_poly("PodInlet", [(x - s * 0.35 * 0 , z) for x, z in rrect(0, 0.215, 0.085, 0.075, 0.05, n=2)],
                  (s * 0.35, -0.161, 0), (1, 0, 0), Z, BLACK, lift=0.0)
        # side stripe + number on the sidepod flank
        roundel("7", (s * 0.47, 0.12, 0.215), (0, s, 0), Z, 0.075, WHITE, BLACK)
        # mirrors on stalks
        cyl("MirrorStalk", (s * 0.30, -0.10, 0.30), (s * 0.33, -0.12, 0.42), 0.01, CARBON, seg=4, caps=(False, False))
        box("Mirror", (s * 0.34, -0.13, 0.44), (0.1, 0.035, 0.055), PAINT, bevel=0.012)
        box("MirrorGlass", (s * 0.34, -0.112, 0.44), (0.08, 0.004, 0.04), CHROME, bevel=0.0)
    # floor / plank under everything
    shaped_box("Floor", lambda sx, sy, sz: (sx * (0.20 if sy < 0 else 0.42), -0.45 if sy < 0 else 0.70,
                                            0.075 if sz < 0 else 0.11), CARBON, bevel=0.0)
    # number on the nose top
    nose_up = Vector((0, 0.28, 0.05)).normalized()
    roundel("7", (0, -0.58, 0.3775), X, nose_up, 0.065, WHITE, BLACK, lift=0.005)
    # ---------- front wing
    fw_y0, fw_y1 = -1.30, -1.15
    shaped_box("FrontWing", lambda sx, sy, sz: (sx * 0.52, fw_y0 if sy < 0 else fw_y1, (0.06 if sy < 0 else 0.07) +
                                                (0.0 if sz < 0 else 0.02)), ACCENT, bevel=0.008, seg=1)
    shaped_box("FrontFlap", lambda sx, sy, sz: (sx * 0.5, -1.17 if sy < 0 else -1.09, (0.10 if sy < 0 else 0.13) +
                                                (0.0 if sz < 0 else 0.014)), STRIPE, bevel=0.0)
    for s in (-1, 1):
        bbox("FWEndplate", (min(s * 0.515, s * 0.535), -1.32, 0.04), (max(s * 0.515, s * 0.535), -1.07, 0.16), STRIPE,
             bevel=0.006)
        beam("FWPylon", (s * 0.05, -1.12, 0.2), (s * 0.07, -1.2, 0.085), 0.015, 0.06, CARBON, side=X, bevel=0.0)
    # ---------- rear wing on two pylons
    rw_z = 0.66
    shaped_box("RearWing", lambda sx, sy, sz: (sx * 0.40, 0.98 if sy < 0 else 1.18, (rw_z + 0.01 if sy < 0 else rw_z) +
                                               (0.0 if sz < 0 else 0.03)), ACCENT, bevel=0.01, seg=1)
    shaped_box("RearFlap", lambda sx, sy, sz: (sx * 0.40, 1.08 if sy < 0 else 1.18, (rw_z + 0.07 if sy < 0 else rw_z + 0.12)
                                               + (0.0 if sz < 0 else 0.018)), STRIPE, bevel=0.0)
    for s in (-1, 1):
        bbox("RWEndplate", (min(s * 0.40, s * 0.425), 0.92, 0.42), (max(s * 0.40, s * 0.425), 1.22, 0.84), PAINT,
             bevel=0.008)
        roundel("7", (s * 0.425, 1.07, 0.62), (0, s, 0), Z, 0.07, WHITE, BLACK)
        beam("RWPylon", (s * 0.08, 0.98, 0.25), (s * 0.08, 1.08, rw_z + 0.01), 0.02, 0.08, CARBON, side=X, bevel=0.0)
    # gearbox, rain light, exhausts
    bbox("Gearbox", (-0.09, 0.95, 0.12), (0.09, 1.16, 0.28), CARBON, bevel=0.015)
    bbox("RainLight", (-0.035, 1.16, 0.15), (0.035, 1.175, 0.20), TAILLIGHT, bevel=0.0)
    for s in (-1, 1):
        cyl("Exhaust", (s * 0.06, 0.92, 0.30), (s * 0.08, 1.12, 0.36), 0.026, CHROME, seg=8, caps=(True, False))
        disc("ExhaustHole", (s * 0.08, 1.12, 0.36), Vector((0.02, 0.2, 0.06)).normalized(), 0.02, BLACK, seg=8)
    # ---------- suspension: wishbones + pushrods to each hub
    for (yy, tr) in ((FY, FT), (RY, RT)):
        for s in (-1, 1):
            hub = Vector((s * (tr - 0.06), yy, WR))
            inner_x = 0.14 if yy < 0 else 0.12
            for dz, (dy0, dy1) in ((-0.05, (-0.1, 0.1)), (0.05, (-0.08, 0.08))):
                for dy in (dy0, dy1):
                    beam("Wishbone", (s * inner_x, yy + dy, WR + dz - (0.03 if yy > 0 else 0.0)), hub + Vector((0, 0, dz)),
                         0.014, 0.014, CARBON, side=Z, bevel=0.0)
            beam("Pushrod", hub + Vector((-s * 0.02, 0, -0.04)), (s * inner_x, yy, 0.30), 0.012, 0.012, CHROME, side=Y,
                 bevel=0.0)
            cyl("Upright", hub + Vector((0, 0, -0.08)), hub + Vector((0, 0, 0.08)), 0.025, METAL, seg=6)

    body = collapse("Body", GROUP)
    weather(body, 10, 41, [(GRIME, 2, (2.0, 4.0)), (mat("Scuff", "c7c3b8", 0.6), 1, (4.0, 7.0))], {"Paint"},
            bottom_bias=2.5, sides=("x", "x", "y"), size=(0.012, 0.03))

    def sidewall(name, W, rim_r):
        w = W / 2
        ring(name + "_Mark", (0.985 * w, 0, 0), X, rim_r + 0.03, rim_r + 0.048, 0.004, MARK, seg=18, sides=(1,))
    RIM = mat("RimPaint", "c9ccd2", 0.25, metal=1.0)
    wk = dict(R=WR, rim_r=0.15, tread="slick", rim_style="race", rim_paint=RIM, steps=18, rim_steps=14, cap=ACCENT,
              extra=sidewall)
    wheels = place_wheels([("WheelFL", FT, FY, WR), ("WheelFR", -FT, FY, WR)], W=0.2, **wk)
    wheels += place_wheels([("WheelRL", RT, RY, WR), ("WheelRR", -RT, RY, WR)], W=0.30, **wk)
    steering = build_steering(STEER, STEER_AX, R=0.06, spokes=4)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat]
    return objs, {"wheel_radius": WR}, SEAT


def flame_shape(L, h, tongues):
    """Flame decal outline: flat front edge at u=0 spanning v in [-h, h], tongues licking back (+u).
    tongues: [(v_centre, length, half_thickness)] from top to bottom."""
    pts = [(0.0, -h), (0.0, h)]
    prev_v = h
    for i, (c, ln, t) in enumerate(tongues):
        valley_u = L * (0.28 + 0.1 * (i % 2))
        top_v = min(prev_v, c + t)
        pts.append((valley_u, top_v))
        pts.append((ln * 0.62, c + t * 0.55))
        pts.append((ln, c - t * 0.2))          # tip, drooping a little
        pts.append((ln * 0.55, c - t * 0.75))
        prev_v = c - t
    pts.append((L * 0.3, -h))
    return pts


def build_monster_truck():
    PAINT = mat("Paint", "1f63e6", 0.28, coat=0.8)
    FLAME1 = mat("FlameOrange", "ff6a12", 0.3, coat=0.6)
    FLAME2 = mat("FlameYellow", "ffd21a", 0.3, coat=0.6)
    FRAME = mat("Frame", "2c2e33", 0.4, metal=0.6)
    SPRING = mat("Spring", "ff7a14", 0.35, coat=0.5)
    MUD = mat("Mud", "5b4631", 0.95)
    RIMP = mat("RimPaint", "c8ff2e", 0.3, coat=0.6)

    WR = 0.55
    TR = 0.80
    FY, RY = -0.95, 0.95
    HW = 0.56
    zb = 1.00
    BELT, ROOF0, ROOF1 = 1.40, 1.69, 1.75
    SEAT = Vector((0.0, 0.03, 1.14))
    STEER = SEAT + Vector((0, -0.29, 0.10))
    STEER_AX = Vector((0, 0.6, 0.8))
    WS0, WS1 = -0.38, -0.17
    CB = 0.32                    # cab back
    BED0, BED1 = 0.36, 1.28

    new_group()
    # ---------- chassis: tube frame, axles with pumpkins, 4-links, coilovers
    for s in (-1, 1):
        tube("FrameRail", [(s * 0.32, -1.30, 0.88), (s * 0.32, -0.6, 0.86), (s * 0.32, 0.6, 0.86), (s * 0.32, 1.30, 0.9)],
             0.04, FRAME, sides=4, rad=0.0)
    for y in (-1.15, -0.45, 0.45, 1.15):
        tube("CrossTube", [(-0.32, y, 0.87), (0.32, y, 0.87)], 0.03, FRAME, sides=4, rad=0.0)
    for yy in (FY, RY):
        cyl("AxleTube", (-TR + 0.2, yy, WR), (TR - 0.2, yy, WR), 0.06, CHROME, seg=8)
        ball("Pumpkin", (0.0, yy, WR), 0.13, CHROME, seg=8, rings_=5)
        cyl("PumpkinCover", (0.0, yy - math.copysign(0.09, -yy), WR), (0.0, yy - math.copysign(0.14, -yy), WR), 0.09,
            FRAME, seg=10)
        for s in (-1, 1):
            cyl("HubCarrier", (s * (TR - 0.2), yy, WR), (s * (TR - 0.12), yy, WR), 0.1, FRAME, seg=6)
            # trailing links up to the frame
            tube("Link", [(s * 0.28, yy, WR - 0.05), (s * 0.32, yy * 0.45, 0.82)], 0.022, FRAME, sides=5, rad=0.0)
            # coilover: black body, chrome shaft, orange spring rings
            top = Vector((s * 0.45, yy - math.copysign(0.12, yy), 1.02))
            bot = Vector((s * 0.52, yy, WR + 0.08))
            d = (top - bot).normalized()
            cyl("ShockBody", bot, bot + d * 0.22, 0.035, BLACK, seg=5)
            cyl("ShockRod", bot + d * 0.2, top, 0.015, CHROME, seg=5, caps=(False, False))
            for k in range(4):
                ring("SpringCoil", bot + d * (0.07 + k * 0.05), d, 0.045, 0.062, 0.024, SPRING, seg=8, sides=(0,))
            box("ShockMount", top, (0.06, 0.06, 0.06), FRAME, bevel=0.0)
    tube("Driveshaft", [(0, FY + 0.15, WR + 0.02), (0, -0.3, 0.8)], 0.03, CHROME, sides=6, rad=0.0)
    tube("Driveshaft", [(0, RY - 0.15, WR + 0.02), (0, 0.3, 0.8)], 0.03, CHROME, sides=6, rad=0.0)
    bbox("Transfer", (-0.15, -0.35, 0.72), (0.15, 0.35, 0.9), FRAME, bevel=0.02)
    # ---------- body shell: hood/fenders, doors, bed (blue, rounded shoulders)
    hood = [(-1.30, zb + 0.02), (WS0, zb), (WS0, BELT), (-1.22, 1.355), (-1.30, 1.32)]
    shoulder_prism("Hood", hood, HW, PAINT, inset=0.06, drop=0.05, z_lo=1.25, z_hi=1.36, bevel=0.025, seg=2)
    for s in (-1, 1):
        dprof = [(WS0 - 0.01, zb), (CB, zb), (CB, BELT), (WS0 - 0.01, BELT)]
        prism("Door", dprof, s * (HW - 0.05), s * HW, PAINT, bevel=0.02, seg=1)
        prism("BedSide", [(BED0, zb), (BED1, zb), (BED1, 1.38), (BED0, 1.38)], s * (HW - 0.05), s * HW, PAINT,
              bevel=0.02, seg=1)
        beam("DoorSeam", (s * (HW + 0.002), CB - 0.03, zb + 0.03), (s * (HW + 0.002), CB - 0.03, BELT - 0.01), 0.004,
             0.007, BLACK, side=Y, bevel=0)
        box("DoorHandle", (s * (HW + 0.008), CB - 0.1, BELT - 0.06), (0.016, 0.08, 0.022), CHROME, bevel=0.0)
        # flames: orange outer, yellow core, licking back from the nose
        tongues = [(0.10, 0.95, 0.06), (0.0, 0.7, 0.05), (-0.09, 1.25, 0.06), (-0.17, 0.6, 0.04)]
        f1 = flame_shape(1.0, 0.2, tongues)
        f2 = [(u * 0.78, v * 0.72) for u, v in flame_shape(1.0, 0.2, tongues)]
        o = Vector((s * HW, -1.28, 1.17))
        flat_poly("Flame", [(s * u, v) for u, v in f1], o, (0, s, 0), Z, FLAME1)
        flat_poly("FlameCore", [(s * u, v) for u, v in f2], o, (0, s, 0), Z, FLAME2, lift=0.0045)
        # step bar + mirror
        tube("NerfBar", [(s * (HW - 0.02), -0.3, zb + 0.02), (s * (HW + 0.06), -0.25, zb - 0.06),
                         (s * (HW + 0.06), 0.25, zb - 0.06), (s * (HW - 0.02), 0.3, zb + 0.02)], 0.025, CHROME, sides=5,
             rad=0.05, n=1)
        beam("MirrorArm", (s * (HW - 0.02), WS0 + 0.04, BELT + 0.02), (s * (HW + 0.07), WS0 + 0.03, BELT + 0.07), 0.015,
             0.015, CHROME, side=Y, bevel=0.0)
        box("Mirror", (s * (HW + 0.09), WS0 + 0.03, BELT + 0.09), (0.04, 0.03, 0.09), BLACK, bevel=0.0)
    bbox("BedFloor", (-HW + 0.04, BED0, zb), (HW - 0.04, BED1, zb + 0.06), FRAME, bevel=0.0)
    bbox("Tailgate", (-HW, BED1 - 0.04, zb), (HW, BED1, 1.38), PAINT, bevel=0.02)
    bbox("BedFront", (-HW, BED0, zb), (HW, BED0 + 0.04, 1.38), PAINT, bevel=0.02)
    bbox("CabFloor", (-HW + 0.04, WS0, zb), (HW - 0.04, CB, zb + 0.04), BLACK, bevel=0.0)
    # ---------- cab greenhouse: pillars, roof, glass front/back, open side windows
    for s in (-1, 1):
        beam("APillar", (s * (HW - 0.035), WS0 + 0.01, BELT), (s * (HW - 0.06), WS1, ROOF0), 0.05, 0.05, PAINT,
             bevel=0.012)
        beam("BPillar", (s * (HW - 0.04), CB - 0.025, BELT), (s * (HW - 0.06), CB - 0.025, ROOF0), 0.07, 0.05, PAINT,
             bevel=0.0)
    bbox("CabBack", (-HW + 0.05, CB - 0.05, BELT), (HW - 0.05, CB, ROOF0), PAINT, bevel=0.0)
    shaped_box("Roof", lambda sx, sy, sz: (sx * (HW - (0.04 if sz < 0 else 0.06)), (WS1 - 0.02 if sz > 0 else WS1 - 0.03)
               if sy < 0 else CB + 0.01, ROOF0 - 0.01 if sz < 0 else ROOF1), PAINT, bevel=0.03, seg=2)
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(p) for p in [(-HW + 0.06, WS0 + 0.02, BELT + 0.005), (HW - 0.06, WS0 + 0.02, BELT + 0.005),
                                            (HW - 0.08, WS1 - 0.01, ROOF0 - 0.01), (-HW + 0.08, WS1 - 0.01, ROOF0 - 0.01)]])
    finish_obj("Windshield", bm, WINDOW, smooth=False)
    # KC light bar on the roof
    bbox("LightRack", (-0.42, -0.05, ROOF1), (0.42, -0.01, ROOF1 + 0.03), CHROME, bevel=0.0)
    for x in (-0.32, -0.11, 0.11, 0.32):
        cyl("KCLight", (x, -0.03, ROOF1 + 0.1), (x, -0.08, ROOF1 + 0.1), 0.07, BLACK, seg=8, r1=0.075)
        disc("KCCover", (x, -0.081, ROOF1 + 0.1), -Y, 0.07, AMBER, seg=8)
        box("KCPost", (x, -0.03, ROOF1 + 0.035), (0.025, 0.025, 0.05), CHROME, bevel=0.0)
    # interior
    bbox("Dash", (-HW + 0.05, WS0 - 0.01, BELT - 0.14), (HW - 0.05, WS0 + 0.1, BELT + 0.02), BLACK, bevel=0.02)
    seat_block(SEAT, 0.34, 0.28, SEATM, back_h=0.42, tilt=-8, base_h=SEAT.z - 0.07 - zb - 0.04, base_m=BLACK,
               bolster=False)
    col_end = STEER - STEER_AX * 0.03
    cyl("Column", col_end - STEER_AX * 0.22, col_end, 0.018, BLACK, seg=6, caps=(False, True))
    # roll cage hoop in the bed
    tube("BedCage", [(-0.42, BED0 + 0.1, zb + 0.05), (-0.42, BED0 + 0.12, 1.62), (0.42, BED0 + 0.12, 1.62),
                     (0.42, BED0 + 0.1, zb + 0.05)], 0.03, CHROME, sides=6, rad=0.1, n=2)
    for s in (-1, 1):
        tube("CageBrace", [(s * 0.4, BED0 + 0.13, 1.55), (s * 0.42, BED1 - 0.08, zb + 0.08)], 0.025, CHROME, sides=6,
             rad=0.0)
    # ---------- nose: chrome grille, quad lamps, tube bumper; blower through the hood
    ny = -1.30
    bbox("Grille", (-0.33, ny - 0.02, 1.07), (0.33, ny + 0.01, 1.28), CHROME, bevel=0.012)
    for i in range(4):
        z = 1.10 + i * 0.045
        bbox("GrilleSlot", (-0.30, ny - 0.03, z), (0.30, ny - 0.02, z + 0.022), BLACK, bevel=0.0)
    for s in (-1, 1):
        for x in (s * 0.40, s * 0.50):
            cyl("LampBezel", (x, ny + 0.005, 1.20), (x, ny - 0.02, 1.20), 0.055, CHROME, seg=8, caps=(False, False))
            disc("Headlamp", (x, ny - 0.015, 1.20), -Y, 0.045, HEADLIGHT, seg=8)
        box("Indicator", (s * 0.45, ny - 0.01, 1.10), (0.16, 0.03, 0.04), AMBER, bevel=0.0)
    tube("Bumper", [(-0.6, ny + 0.1, 0.98), (-0.55, ny - 0.1, 0.98), (0.55, ny - 0.1, 0.98), (0.6, ny + 0.1, 0.98)],
         0.045, CHROME, sides=6, rad=0.1, n=2)
    tube("BumperHoop", [(-0.3, ny - 0.1, 0.98), (-0.3, ny - 0.13, 1.12), (0.3, ny - 0.13, 1.12), (0.3, ny - 0.1, 0.98)],
         0.03, CHROME, sides=6, rad=0.08, n=2)
    by = -0.85
    bbox("BlowerBase", (-0.14, by - 0.16, 1.32), (0.14, by + 0.16, 1.40), CHROME, bevel=0.012)
    bbox("Blower", (-0.12, by - 0.14, 1.40), (0.12, by + 0.14, 1.52), CHROME, bevel=0.02, seg=2)
    for k in range(5):
        y = by - 0.12 + k * 0.06
        bbox("BlowerRib", (-0.125, y - 0.008, 1.41), (0.125, y + 0.008, 1.515), METAL, bevel=0.0)
    shaped_box("Scoop", lambda sx, sy, sz: (sx * (0.13 if sz < 0 else 0.11), (by - 0.16 if sz < 0 else by - 0.2) if sy < 0
               else by + 0.12, 1.52 if sz < 0 else 1.64), BLACK, bevel=0.015, seg=1)
    bbox("ScoopMouth", (-0.09, by - 0.205, 1.55), (0.09, by - 0.19, 1.62), FRAME, bevel=0.0)
    for s in (-1, 1):
        cyl("Stack", (s * 0.40, CB + 0.08, zb + 0.1), (s * 0.40, CB + 0.08, 1.95), 0.035, CHROME, seg=8,
            caps=(True, False))
        cyl("StackTip", (s * 0.40, CB + 0.08, 1.95), (s * 0.40, CB + 0.11, 2.0), 0.035, CHROME, seg=8, r1=0.045,
            caps=(False, False))
    # tail lights
    for s in (-1, 1):
        bbox("TailLamp", (min(s * 0.42, s * 0.54), BED1, 1.18), (max(s * 0.42, s * 0.54), BED1 + 0.015, 1.32),
             TAILLIGHT, bevel=0.0)
    text("Tailgate", "MONSTER", 0.12, (0, BED1, 1.24), (-1, 0, 0), Z, FLAME2, font="Arial Black.ttf", res=1)

    body = collapse("Body", GROUP)
    weather(body, 12, 51, [(MUD, 3, (1.5, 3.5))], {"Paint", "FlameOrange", "FlameYellow"}, bottom_bias=3.0,
            sides=("x", "x", "y"), size=(0.025, 0.06))

    wk = dict(R=WR, W=0.46, rim_r=0.26, tread="monster", rim_style="beadlock", rim_paint=RIMP, steps=18, rim_steps=14,
              cap=CHROME, depth=0.05)
    wheels = place_wheels([("WheelFL", TR, FY, WR), ("WheelFR", -TR, FY, WR), ("WheelRL", TR, RY, WR),
                           ("WheelRR", -TR, RY, WR)], **wk)
    steering = build_steering(STEER, STEER_AX, R=0.075)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat]
    return objs, {"wheel_radius": WR}, SEAT


def octagon(r):
    return [(math.cos(pi / 8 + k * pi / 4) * r, math.sin(pi / 8 + k * pi / 4) * r) for k in range(8)]


def build_ice_cream_truck():
    MINT = mat("Paint", "8fdcc0", 0.32, coat=0.7)
    CREAM = mat("Cream", "fff1d8", 0.35, coat=0.6)
    PINK = mat("Pink", "ff8fc0", 0.32, coat=0.6)
    SKY = mat("SkyBlue", "8cc9ff", 0.32, coat=0.6)
    CONE = mat("Waffle", "e3b066", 0.6)
    CONE2 = mat("WaffleDark", "bf8740", 0.65)
    SCOOP = mat("Strawberry", "ffb0cf", 0.45, coat=0.3)
    CHERRY = mat("Cherry", "d81b33", 0.15, coat=0.8)
    INTERIOR = mat("Interior", "d9cdb8", 0.6)
    STOP = mat("StopRed", "d62030", 0.3, coat=0.5)
    CHOC = mat("Chocolate", "6b3b22", 0.4, coat=0.3)
    STICK = mat("Stick", "e8cf9a", 0.7)

    WR = 0.27
    FY, RY = -1.02, 0.86
    TR = 0.44
    HW = 0.52
    zb = 0.22
    FLOOR = 0.30
    BELT = 0.70            # mint below, cream above
    ROOF0, ROOF1 = 1.36, 1.44
    CAB0, CAB1 = -1.05, -0.30
    BOX1 = 1.32
    SEAT = Vector((0.22, -0.56, 0.58))
    STEER = SEAT + Vector((0, -0.29, 0.10))
    STEER_AX = Vector((0, 0.42, 0.9))
    WIN0, WIN1, WZ0, WZ1 = -0.20, 0.46, 0.74, 1.14   # serving window
    CONE_Y = 0.55

    new_group()
    # ---------- short rounded hood + grille + bumper
    hood = [(-1.38, zb + 0.02)] + arch(FY, WR, 0.32, zb, 7)[:4] + [(CAB0 + 0.02, 0.56), (CAB0 + 0.02, 0.66),
                                                                  (-1.30, 0.64), (-1.38, 0.58)]
    hw_h = 0.47
    shoulder_prism("Hood", hood, hw_h, MINT, inset=0.06, drop=0.05, z_lo=0.5, z_hi=0.66, bevel=0.03, seg=1)
    ny = -1.38
    bbox("Grille", (-0.2, ny - 0.015, 0.30), (0.2, ny + 0.01, 0.54), CHROME, bevel=0.015)
    for k in range(7):
        x = -0.15 + k * 0.05
        bbox("GrilleBar", (x - 0.008, ny - 0.025, 0.32), (x + 0.008, ny - 0.012, 0.52), METAL, bevel=0.0)
    for s in (-1, 1):
        cyl("LampBezel", (s * 0.34, ny + 0.02, 0.48), (s * 0.34, ny - 0.03, 0.48), 0.07, CHROME, seg=10, caps=(False, True))
        disc("Headlamp", (s * 0.34, ny - 0.031, 0.48), -Y, 0.055, HEADLIGHT, seg=10)
        box("Indicator", (s * 0.34, ny - 0.005, 0.35), (0.09, 0.03, 0.04), AMBER, bevel=0.0)
    shaped_box("Bumper", lambda sx, sy, sz: (sx * (0.50 if sy > 0 else 0.48), ny - (0.09 if sy < 0 else -0.02),
                                             0.17 if sz < 0 else 0.29), CHROME, bevel=0.03, seg=2)
    # ---------- cab: lower panels with the front arch, big open doorway either side
    for s in (-1, 1):
        lp = [(CAB0, zb)] + [p for p in arch(FY, WR, 0.32, zb, 7) if p[0] >= CAB0 - 1e-6] + [(-0.66, zb), (-0.66, 0.62),
                                                                                              (CAB0, 0.62)]
        lp = [(CAB0, 0.62), (CAB0, WR + 0.32 * 0.99)] + [p for p in arch(FY, WR, 0.32, zb, 7) if p[0] > FY] + \
             [(-0.66, zb), (-0.66, 0.62)]
        prism("CabPanel", lp, s * (HW - 0.05), s * HW, MINT, bevel=0.02, seg=1)
        bbox("FrontPost", (min(s * (HW - 0.05), s * HW), CAB0, 0.62), (max(s * (HW - 0.05), s * HW), CAB0 + 0.07, ROOF0),
             CREAM, bevel=0.015)
        bbox("DoorPost", (min(s * (HW - 0.05), s * HW), -0.36, zb), (max(s * (HW - 0.05), s * HW), -0.30, ROOF0),
             MINT, bevel=0.015)
        bbox("DoorStep", (min(s * (HW - 0.12), s * (HW + 0.02)), -0.66, zb - 0.02), (max(s * (HW - 0.12), s * (HW + 0.02)),
                                                                                    -0.36, zb + 0.03), ALU, bevel=0.0)
        arc_band("ArchLipF", FY, WR, 0.32, 0.345, s * (HW - 0.02), s * (HW + 0.012), CREAM, a0=0.2, a1=pi * 0.62,
                 steps=5, bevel=0.0)
        tube("GrabBar", [(s * (HW - 0.02), -0.37, 0.4), (s * (HW - 0.02), -0.37, 1.0)], 0.012, CHROME, sides=5, rad=0)
        beam("MirrorArm", (s * (HW - 0.01), CAB0 + 0.04, 0.95), (s * (HW + 0.08), CAB0 - 0.02, 0.95), 0.015, 0.015,
             CHROME, side=Z, bevel=0.0)
        box("Mirror", (s * (HW + 0.09), CAB0 - 0.02, 0.88), (0.035, 0.04, 0.16), CHROME, bevel=0.008)
    bbox("Cowl", (-HW, CAB0, 0.56), (HW, CAB0 + 0.08, 0.70), MINT, bevel=0.02)
    bbox("Floor", (-HW + 0.03, CAB0, zb), (HW - 0.03, BOX1, FLOOR), INTERIOR, bevel=0.0)
    bbox("Dash", (-HW + 0.05, CAB0 + 0.06, 0.56), (HW - 0.05, CAB0 + 0.16, 0.72), CHOC, bevel=0.02)
    glass = [(-HW + 0.05, CAB0 + 0.03, 0.71), (HW - 0.05, CAB0 + 0.03, 0.71), (HW - 0.05, CAB0 + 0.09, ROOF0 - 0.02),
             (-HW + 0.05, CAB0 + 0.09, ROOF0 - 0.02)]
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(p) for p in glass])
    finish_obj("Windshield", bm, WINDOW, smooth=False)
    beam("Pillar", (0, CAB0 + 0.03, 0.70), (0, CAB0 + 0.09, ROOF0), 0.03, 0.03, CREAM, bevel=0.0)
    seat_block(SEAT, 0.28, 0.26, PINK, back_h=0.34, tilt=-8, base_h=SEAT.z - 0.07 - FLOOR, base_m=CHROME, bolster=False)
    col_end = STEER - STEER_AX * 0.03
    cyl("Column", col_end - STEER_AX * 0.3, col_end, 0.02, BLACK, seg=6, caps=(False, True))
    bbox("Bulkhead", (-HW + 0.03, -0.36, FLOOR), (HW - 0.03, -0.31, ROOF0), CREAM, bevel=0.0)
    # ---------- box body: mint lower, cream upper, pink belt stripe, serving windows both sides
    for s in (-1, 1):
        x0, x1 = min(s * (HW - 0.05), s * HW), max(s * (HW - 0.05), s * HW)
        low = [(-0.31, zb)] + arch(RY, WR, 0.32, zb, 7) + [(BOX1, zb), (BOX1, BELT), (-0.31, BELT)]
        prism("BoxLower", low, s * (HW - 0.05), s * HW, MINT, bevel=0.02, seg=1)
        arc_band("ArchLipR", RY, WR, 0.32, 0.345, s * (HW - 0.02), s * (HW + 0.012), CREAM, a0=0.08, a1=pi - 0.08,
                 steps=6, bevel=0.0)
        bbox("BoxUpperF", (x0, -0.31, BELT), (x1, WIN0, ROOF0), CREAM, bevel=0.012)
        bbox("BoxUpperR", (x0, WIN1, BELT), (x1, BOX1, ROOF0), CREAM, bevel=0.012)
        bbox("BoxHeader", (x0, WIN0, WZ1), (x1, WIN1, ROOF0), CREAM, bevel=0.0)
        bbox("BoxSill", (x0, WIN0, BELT), (x1, WIN1, WZ0), CREAM, bevel=0.0)
        # pink belt stripe all the way round
        bbox("BeltStripe", (min(s * HW, s * (HW + 0.008)), -0.31, BELT - 0.02), (max(s * HW, s * (HW + 0.008)), BOX1,
                                                                                 BELT + 0.03), PINK, bevel=0.0)
        bbox("CabStripe", (min(s * HW, s * (HW + 0.008)), -0.66, BELT - 0.09), (max(s * HW, s * (HW + 0.008)), -0.36,
                                                                                BELT - 0.04), PINK, bevel=0.0)
        # serving counter + window frame + half-open sliding glass
        bbox("Counter", (min(s * (HW - 0.06), s * (HW + 0.09)), WIN0 - 0.02, WZ0 - 0.03),
             (max(s * (HW - 0.06), s * (HW + 0.09)), WIN1 + 0.02, WZ0), CREAM, bevel=0.008)
        for y in (WIN0, WIN1):
            bbox("WinFrame", (min(s * (HW - 0.01), s * (HW + 0.01)), y - 0.015, WZ0), (max(s * (HW - 0.01),
                                                                                          s * (HW + 0.01)), y + 0.015,
                                                                                      WZ1), CHROME, bevel=0.0)
        g = [(s * (HW - 0.03), WIN1 - 0.01, WZ0 + 0.01), (s * (HW - 0.03), (WIN0 + WIN1) / 2 + 0.05, WZ0 + 0.01),
             (s * (HW - 0.03), (WIN0 + WIN1) / 2 + 0.05, WZ1 - 0.01), (s * (HW - 0.03), WIN1 - 0.01, WZ1 - 0.01)]
        bm = bmesh.new()
        bm.faces.new([bm.verts.new(p) for p in g])
        finish_obj("SlideGlass", bm, WINDOW, smooth=False)
        # striped scalloped awning over the window
        n = 8
        aw0, aw1 = WIN0 - 0.04, WIN1 + 0.04
        for k in range(n):
            ya, yb = aw0 + (aw1 - aw0) * k / n, aw0 + (aw1 - aw0) * (k + 1) / n
            m = PINK if k % 2 == 0 else CREAM
            pts = [(s * (HW + 0.005), ya, WZ1 + 0.14), (s * (HW + 0.005), yb, WZ1 + 0.14),
                   (s * (HW + 0.17), yb, WZ1 + 0.04), (s * (HW + 0.17), (ya + yb) / 2, WZ1 + 0.0),
                   (s * (HW + 0.17), ya, WZ1 + 0.04)]
            bm = bmesh.new()
            bm.faces.new([bm.verts.new(p) for p in pts])
            finish_obj("Awning", bm, m, smooth=False)
        for y in (aw0 + 0.02, aw1 - 0.02):
            beam("AwningArm", (s * HW, y, WZ1 - 0.06), (s * (HW + 0.16), y, WZ1 + 0.03), 0.01, 0.01, CHROME, side=Y,
                 bevel=0.0)
        # popsicle menu under the window
        for k, (m, top) in enumerate(((PINK, CHOC), (SKY, CREAM), (CHOC, PINK), (CHERRY, CREAM))):
            yc = WIN0 + 0.08 + k * 0.165
            o = Vector((s * HW, yc, 0.47))
            flat_poly("MenuCard", rrect(0, 0, 0.065, 0.1, 0.02, n=1), o, (0, s, 0), Z, CREAM, lift=0.003)
            flat_poly("Pop", rrect(0, 0.02, 0.03, 0.05, 0.028, n=2), o, (0, s, 0), Z, m, lift=0.005)
            flat_poly("PopDip", [(x, z) for x, z in rrect(0, 0.05, 0.03, 0.022, 0.02, n=2)], o, (0, s, 0), Z, top,
                      lift=0.006)
            flat_poly("PopStick", [(-0.006, -0.07), (0.006, -0.07), (0.006, -0.03), (-0.006, -0.03)], o, (0, s, 0), Z,
                      STICK, lift=0.005)
        flat_poly("SignBoard", rrect(0, 0, 0.36, 0.16, 0.07, n=2), (s * HW, 0.89, 1.0), (0, s, 0), Z, PINK, lift=0.003)
        flat_poly("SignEdge", rrect(0, 0, 0.375, 0.175, 0.08, n=2), (s * HW, 0.89, 1.0), (0, s, 0), Z, SKY, lift=0.0015)
        text("Sign", "ICE", 0.12, (s * HW, 0.89, 1.065), (0, s, 0), Z, CREAM, font="Arial Rounded Bold.ttf", res=1)
        text("Sign", "CREAM", 0.12, (s * HW, 0.89, 0.935), (0, s, 0), Z, CREAM, font="Arial Rounded Bold.ttf", res=1)
    # stop arm folded against the left side, behind the driver's doorway
    o = Vector((HW + 0.02, -0.22, 0.95))
    beam("StopArm", (HW, -0.30, 0.95), (HW + 0.02, -0.16, 0.95), 0.02, 0.02, BLACK, side=Z, bevel=0.0)
    flat_poly("StopSign", octagon(0.085), o, Y, Z, STOP, lift=0.0)
    flat_poly("StopRim", octagon(0.072), o, Y, Z, CREAM, lift=0.002)
    flat_poly("StopIn", octagon(0.064), o, Y, Z, STOP, lift=0.004)
    text("StopText", "STOP", 0.045, o, Y, Z, CREAM, font="Arial Black.ttf", lift=0.006, res=1)
    # interior: freezer chest + soft-serve machine visible through the windows
    bbox("Freezer", (-0.32, -0.20, FLOOR), (0.32, 0.45, 0.68), SKY, bevel=0.02)
    bbox("FreezerLid", (-0.30, -0.18, 0.68), (0.30, 0.43, 0.70), WINDOW, bevel=0.0)
    for k, m in enumerate((PINK, CREAM, CHOC, SKY)):
        bbox("Tub", (-0.26 + k * 0.13, 0.0, 0.62), (-0.16 + k * 0.13, 0.12, 0.67), m, bevel=0.0)
    bbox("SoftServe", (-0.18, 0.62, FLOOR), (0.18, 0.95, 1.05), CHROME, bevel=0.02)
    for x in (-0.08, 0.08):
        cyl("Tap", (x, 0.62, 0.86), (x, 0.58, 0.82), 0.02, CHROME, seg=6)
    # ---------- roof (cream, rounded shoulders, slight overhang) + chime speaker + cone holder
    roof = [(CAB0 - 0.03, ROOF0), (BOX1 + 0.02, ROOF0), (BOX1 + 0.02, ROOF1 - 0.02), (BOX1 - 0.02, ROOF1),
            (CAB0 + 0.02, ROOF1), (CAB0 - 0.03, ROOF1 - 0.03)]
    shoulder_prism("Roof", roof, HW + 0.02, mat("RoofPink", "ffc4dd", 0.32, coat=0.6), inset=0.05, drop=0.03,
                   z_lo=ROOF0, z_hi=ROOF1, bevel=0.02, seg=2)
    cyl("Speaker", (0.0, CAB0 + 0.22, ROOF1 + 0.07), (0.0, CAB0 + 0.0, ROOF1 + 0.07), 0.025, CHROME, seg=8, r1=0.07,
        caps=(True, False))
    box("SpeakerMount", (0.0, CAB0 + 0.16, ROOF1 + 0.03), (0.04, 0.06, 0.06), CHROME, bevel=0.0)
    for x in (-0.3, 0.3):
        box("Marker", (x, CAB0 + 0.0, ROOF1 - 0.02), (0.06, 0.02, 0.025), AMBER, bevel=0.0)
    # ---------- the giant cone: waffle cone, strawberry soft-serve swirl, sprinkles and a cherry
    cb = Vector((0.0, CONE_Y, ROOF1))
    cyl("ConeCup", cb, cb + Z * 0.06, 0.12, CHROME, seg=12, r1=0.10)
    SC = 1.2
    cone_h, cone_r = 0.46 * SC, 0.22 * SC
    prof = [(0.0, 0.03), (cone_h * 0.2, cone_r * 0.22), (cone_h * 0.4, cone_r * 0.4), (cone_h * 0.6, cone_r * 0.6),
            (cone_h * 0.8, cone_r * 0.8), (cone_h, cone_r)]
    vlathe("Cone", prof, cb + Z * 0.02, [CONE, CONE2], steps=16, face_mat=lambda i, k: (i + k) % 2)
    rim_c = cb + Z * (0.02 + cone_h)
    ring("ConeRim", rim_c, Z, cone_r * 0.85, cone_r + 0.02, 0.05, CONE, seg=16, sides=(0, 1, 3))
    swirl = [(h * SC, r * SC) for h, r in [(0.0, 0.215), (0.05, 0.245), (0.11, 0.225), (0.14, 0.17), (0.17, 0.2),
                                           (0.22, 0.185), (0.26, 0.13), (0.29, 0.15), (0.33, 0.13), (0.37, 0.08),
                                           (0.41, 0.07), (0.45, 0.035), (0.50, 0.012)]]
    vlathe("Swirl", swirl, rim_c + Z * 0.01, SCOOP, steps=16)
    # sprinkles scattered over the swirl
    rnd = random.Random(9)
    cols = [SKY, CREAM, mat("SprinkleYellow", "ffe14a", 0.4), MINT, CHERRY]
    for k in range(22):
        t = rnd.uniform(0.02, 0.36) * SC
        r = None
        for (h0, r0), (h1, r1) in zip(swirl, swirl[1:]):
            if h0 <= t <= h1:
                r = r0 + (r1 - r0) * (t - h0) / (h1 - h0)
        a = rnd.uniform(0, 2 * pi)
        p = rim_c + Z * (0.01 + t) + Vector((math.cos(a), math.sin(a), 0)) * (r + 0.004)
        box("Sprinkle", p, (0.012, 0.035, 0.012), cols[k % len(cols)], bevel=0.0,
            rot=(rnd.uniform(0, 180), rnd.uniform(0, 180), rnd.uniform(0, 180)))
    top = rim_c + Z * 0.52 * SC
    ball("Cherry", top + Z * 0.04, 0.055, CHERRY, seg=10, rings_=6)
    tube("CherryStem", [top + Z * 0.09, top + Z * 0.14 + Y * 0.02, top + Z * 0.17 + Y * 0.07], 0.007, CHOC, sides=4,
         rad=0.03, n=2)
    # ---------- rear: door with window, lights, bumper, ladder
    ry = BOX1
    bbox("RearWall", (-HW, ry - 0.04, zb), (HW, ry, ROOF0), CREAM, bevel=0.015)
    bbox("RearLower", (-HW, ry - 0.045, zb), (HW, ry + 0.002, BELT), MINT, bevel=0.012)
    bbox("RearStripe", (-HW, ry, BELT - 0.02), (HW, ry + 0.008, BELT + 0.03), PINK, bevel=0.0)
    bbox("RearDoor", (-0.24, ry, 0.3), (0.24, ry + 0.012, 1.25), CREAM, bevel=0.006)
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(p) for p in [(-0.18, ry + 0.014, 0.9), (0.18, ry + 0.014, 0.9), (0.18, ry + 0.014, 1.18),
                                            (-0.18, ry + 0.014, 1.18)]])
    finish_obj("RearWindow", bm, mat("DarkGlass", "1e2a33", 0.05), smooth=False)
    box("RearHandle", (0.17, ry + 0.02, 0.72), (0.08, 0.02, 0.025), CHROME, bevel=0.0)
    for s in (-1, 1):
        cyl("TailLamp", (s * 0.40, ry, 0.52), (s * 0.40, ry + 0.02, 0.52), 0.045, TAILLIGHT, seg=10, caps=(False, True))
        cyl("TailLamp2", (s * 0.40, ry, 0.40), (s * 0.40, ry + 0.02, 0.40), 0.035, AMBER, seg=8, caps=(False, True))
    shaped_box("RearBumper", lambda sx, sy, sz: (sx * 0.5, ry + (0.08 if sy > 0 else -0.01), 0.17 if sz < 0 else 0.28),
               CHROME, bevel=0.025, seg=1)
    cyl("AxleF", (-TR, FY, WR), (TR, FY, WR), 0.035, BLACK, seg=6, caps=(False, False))
    cyl("AxleR", (-TR, RY, WR), (TR, RY, WR), 0.045, BLACK, seg=6, caps=(False, False))

    body = collapse("Body", GROUP)
    weather(body, 10, 61, [(GRIME, 3, (2.0, 3.5)), (RUST, 1, (1.0, 1.5))], {"Paint", "Cream"}, bottom_bias=3.0,
            sides=("x", "x", "y"), size=(0.015, 0.035))

    wk = dict(R=WR, W=0.2, rim_r=0.16, tread="road", rim_style="dog", rim_paint=SKY, steps=16, rim_steps=12, lugs=5,
              cap=CHROME, grooves=2)
    wheels = place_wheels([("WheelFL", TR, FY, WR), ("WheelFR", -TR, FY, WR), ("WheelRL", TR, RY, WR),
                           ("WheelRR", -TR, RY, WR)], **wk)
    steering = build_steering(STEER, STEER_AX, R=0.085, rim_m=PINK)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat]
    return objs, {"wheel_radius": WR}, SEAT


VEHICLES = {
    "fire_truck": build_fire_truck,
    "police_car": build_police_car,
    "garbage_truck": build_garbage_truck,
    "race_car": build_race_car,
    "monster_truck": build_monster_truck,
    "ice_cream_truck": build_ice_cream_truck,
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
