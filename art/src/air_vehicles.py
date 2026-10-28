# Flying vehicles: Santa's sleigh, stunt plane, rescue helicopter, retro rocket, hoverboard.
# Run: blender --background --python art/src/air_vehicles.py [-- sleigh plane helicopter rocket hoverboard]
#      (no names = build all). Set AV_CHECK=<dir> to also render preview shots with a seated pilot.
# Same conventions as buggy.py: game units (character = 0.55 tall), Blender Z-up, every vehicle faces
# -Y in Blender (= Godot +Z), its left is +X. Top-level nodes only, no parenting, no UVs.
# Each vehicle exports assets/vehicles/<name>.glb plus a 512x512 transparent thumbnail <name>.png.
#
#   Every vehicle:  Body  - the static mesh; origin = ground centre (where it rests when parked).
#                   Seat  - empty at the top of the seat cushion (the pilot's hips).
#   sleigh:     Deer1Body/Deer2Body (origin at the body centre), Deer<n>LegFL/FR/BL/BR (origin at the
#               shoulder/hip joint), Deer<n>Head (origin at the neck joint). Deer1 is Rudolph (NoseGlow).
#               Sparkles - empty under the runners for magic dust.
#   plane:      Propeller (origin at the hub, spins about local Z), AileronL/AileronR (hinge along local X),
#               Elevator (hinge along local X), Rudder (hinge along local Z / Godot Y).
#   helicopter: Rotor (origin at the hub, spins about Y), TailRotor (origin at its hub, spins about X).
#   rocket:     Flame - empty at the nozzle exit. Stands upright on three fins.
#   hoverboard: Seat is on the deck top where the rider STANDS; HoverFX - empty under the board.
import bpy, bmesh, math, os, random, sys
from mathutils import Vector, Euler, Quaternion, Matrix
from mathutils.bvhtree import BVHTree

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "assets", "vehicles")
CHARS = os.path.join(ROOT, "assets", "characters")
CHECK = os.environ.get("AV_CHECK")
os.makedirs(OUT, exist_ok=True)

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


# ---------------------------------------------------------------- materials
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
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.diffuse_color = lin(color)
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.12
    if emit:
        b.inputs["Emission Color"].default_value = lin(emit)
        b.inputs["Emission Strength"].default_value = emit_strength
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
        m.use_backface_culling = False
    mats[name] = m
    return m


def common_mats():
    return dict(
        CHROME=mat("Chrome", "f2f2f5", 0.07, metal=1.0),
        METAL=mat("Metal", "4a4e55", 0.36, metal=1.0),
        RUBBER=mat("Rubber", "1c1c1e", 0.82),
        BLACK=mat("Black", "151517", 0.5),
        RUST=mat("Rust", "6b2c12", 0.92, metal=0.15),
        GLASS=mat("Glass", "cfe9ff", 0.04, alpha=0.14),
    )


# ---------------------------------------------------------------- object helpers
class Group:
    def __init__(self):
        self.parts = []


GROUP = None


def new_group():
    global GROUP
    GROUP = Group()
    return GROUP


def TRS(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    if not isinstance(scale, (tuple, list, Vector)):
        scale = (scale, scale, scale)
    S = Matrix.Diagonal((*scale, 1.0))
    R = Euler([math.radians(a) for a in rot]).to_matrix().to_4x4()
    return Matrix.Translation(Vector(loc)) @ R @ S


def finish_obj(name, bm, m, smooth=True, bevel=0.0, seg=2, angle=30, M=None, mat_fn=None, flip=False):
    if M is not None:
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
        if M.to_3x3().determinant() < 0:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    if flip:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ms = list(m) if isinstance(m, (list, tuple)) else [m]
    for mm in ms:
        me.materials.append(mm)
    for p in me.polygons:
        p.use_smooth = smooth if not callable(smooth) else smooth(p)
        if mat_fn:
            p.material_index = mat_fn(p)
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


def smooth_by_angle(ob, deg=35):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(deg), keep_sharp_edges=True)
    return ob


def shaped_box(name, corner_fn, m, bevel=0.02, seg=2, M=None, angle=30):
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
    return finish_obj(name, bm, m, bevel=bevel, seg=seg, M=M, angle=angle)


def box(name, c, size, m, bevel=0.015, seg=2, rot=None, M=None):
    c, h = Vector(c), Vector(size) / 2
    q = Euler([math.radians(a) for a in rot]).to_matrix() if rot else None

    def fn(sx, sy, sz):
        p = Vector((sx * h.x, sy * h.y, sz * h.z))
        return c + (q @ p if q else p)
    return shaped_box(name, fn, m, bevel, seg, M=M)


def ring_verts(bm, c, axis, r, seg, phase=0.5):
    axis = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    return [bm.verts.new(c + (u * math.cos(2 * math.pi * (i + phase) / seg) + v * math.sin(2 * math.pi * (i + phase) / seg)) * r)
            for i in range(seg)]


def cyl(name, p0, p1, r, m, seg=12, r1=None, caps=(True, True), bevel=0.0, smooth_sides=True, M=None):
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
    return finish_obj(name, bm, m, smooth=(lambda p: smooth_sides and len(p.vertices) == 4), bevel=bevel, seg=1, M=M)


def ring(name, c, axis, r_in, r_out, depth, m, seg=20, bevel=0.0, sides=(0, 1, 2, 3), M=None):
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
    return finish_obj(name, bm, m, bevel=bevel, seg=1, angle=50, M=M,
                      smooth=lambda p: abs(p.normal.dot(axis)) < 0.7)


def disc(name, c, normal, r, m, seg=16, M=None):
    """Flat round face (one-sided, facing along normal)."""
    bm = bmesh.new()
    vs = ring_verts(bm, Vector(c), normal, r, seg)
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(Vector(normal)) < 0:
        f.normal_flip()
    return finish_obj(name, bm, m, smooth=False, M=M)


def fillet(pts, rad, n=3, closed=False):
    pts = [Vector(p) for p in pts]
    N = len(pts)
    out = [] if closed else [pts[0]]
    idx = range(N) if closed else range(1, N - 1)
    for i in idx:
        A, P, B = pts[i - 1], pts[i], pts[(i + 1) % N]
        r = rad[i] if isinstance(rad, (list, tuple)) else rad
        da, db = A - P, B - P
        if r <= 0:
            out.append(P)
            continue
        a = P + da.normalized() * min(r, da.length * 0.45)
        b = P + db.normalized() * min(r, db.length * 0.45)
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * a + 2 * (1 - t) * t * P + t * t * b)
    if not closed:
        out.append(pts[-1])
    return out


def tube(name, pts, r, m, sides=8, rad=0.09, n=3, closed=False, up=None, caps=True, M=None, smooth=None):
    """Bent tube swept along a filleted polyline. r may be a number or a function of t in [0, 1]."""
    pts = fillet(pts, rad, n, closed) if rad else [Vector(p) for p in pts]
    N = len(pts)
    L = [0.0]
    for a, b in zip(pts, pts[1:]):
        L.append(L[-1] + (b - a).length)
    bm = bmesh.new()
    rings, u = [], None
    for i, p in enumerate(pts):
        if closed:
            t = ((pts[(i + 1) % N] - p).normalized() + (p - pts[i - 1]).normalized()).normalized()
        elif i == 0:
            t = (pts[1] - pts[0]).normalized()
        elif i == N - 1:
            t = (pts[-1] - pts[-2]).normalized()
        else:
            t = ((pts[i + 1] - p).normalized() + (p - pts[i - 1]).normalized()).normalized()
        if up is not None:
            u = t.cross(Vector(up)).normalized()
        elif u is None:
            ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            u = t.cross(ref).normalized()
        else:
            u = (u - t * t.dot(u)).normalized()
        v = t.cross(u)
        rr = r(L[i] / L[-1]) if callable(r) else r
        rings.append([bm.verts.new(p + (u * math.cos(2 * math.pi * k / sides) + v * math.sin(2 * math.pi * k / sides)) * rr)
                      for k in range(sides)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for A, B in pairs:
        for k in range(sides):
            j = (k + 1) % sides
            bm.faces.new([A[k], A[j], B[j], B[k]])
    if not closed and caps:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=smooth or (lambda p: len(p.vertices) == 4), M=M)


def se_pts(c, u, v, a, b, n=2.0, seg=24, phase=0.0):
    """Superellipse ring: centre c, axes u (half-size a) and v (half-size b), squareness n (2 = ellipse)."""
    pts = []
    for i in range(seg):
        t = 2 * math.pi * (i + phase) / seg
        ct, st = math.cos(t), math.sin(t)
        pts.append(Vector(c) + Vector(u) * a * math.copysign(abs(ct) ** (2 / n), ct)
                   + Vector(v) * b * math.copysign(abs(st) ** (2 / n), st))
    return pts


def loft_bm(secs, cap0=True, cap1=True, closed=False, wrap=True):
    """Skin a list of rings (lists of points with equal counts) or single points (poles)."""
    bm = bmesh.new()
    rings = []
    for s in secs:
        if isinstance(s, Vector):
            rings.append([bm.verts.new(s)])
        else:
            rings.append([bm.verts.new(Vector(p)) for p in s])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for A, B in pairs:
        n = max(len(A), len(B))
        rng = range(n) if wrap else range(n - 1)
        for i in rng:
            j = (i + 1) % n
            if len(A) == 1:
                bm.faces.new([A[0], B[i], B[j]][::-1])
            elif len(B) == 1:
                bm.faces.new([A[i], A[j], B[0]])
            else:
                bm.faces.new([A[i], A[j], B[j], B[i]])
    if not closed and wrap:
        if cap0 and len(rings[0]) > 2:
            bm.faces.new(rings[0][::-1])
        if cap1 and len(rings[-1]) > 2:
            bm.faces.new(rings[-1])
    if wrap:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def loft(name, secs, m, cap0=True, cap1=True, smooth=True, bevel=0.0, mat_fn=None, M=None, flip=False, wrap=True,
         closed=False):
    bm = loft_bm(secs, cap0, cap1, closed=closed, wrap=wrap)
    if smooth is True and (cap0 or cap1):
        smooth = lambda p: len(p.vertices) <= 4
    return finish_obj(name, bm, m, smooth=smooth, bevel=bevel, mat_fn=mat_fn, M=M, flip=flip)


def lathe(name, prof, m, seg=24, M=None, smooth=True, mat_fn=None, cap0=True, cap1=True, flip=False):
    """Revolve a (radius, height) profile about local +Z. radius 0 = pole."""
    secs = []
    for r, h in prof:
        if r < 1e-6:
            secs.append(Vector((0, 0, h)))
        else:
            secs.append([Vector((math.cos(2 * math.pi * i / seg) * r, math.sin(2 * math.pi * i / seg) * r, h))
                         for i in range(seg)])
    return loft(name, secs, m, cap0=cap0, cap1=cap1, smooth=smooth, mat_fn=mat_fn, M=M, flip=flip)


def blob(name, c, r, m, seg=12, rings=7, rot=(0, 0, 0), squash=None, M=None):
    """Ellipsoid with radii r=(rx, ry, rz). squash(z) optionally scales each latitude ring."""
    prof = []
    for k in range(rings + 1):
        a = math.pi * k / rings
        rr = math.sin(a)
        if squash:
            rr *= squash(-math.cos(a))
        prof.append((rr, -math.cos(a)))
    if not isinstance(r, (tuple, list, Vector)):
        r = (r, r, r)
    Mx = TRS(c, rot, r)
    if M is not None:
        Mx = M @ Mx
    return lathe(name, prof, m, seg=seg, M=Mx)


def extrude(name, outline, depth, m, bevel=0.0, seg=2, M=None, angle=30, smooth=False, mat_fn=None):
    """Prism from a 2D outline [(y, z)] in the YZ plane, depth along X (centred)."""
    bm = bmesh.new()
    a = [bm.verts.new((-depth / 2, p[0], p[1])) for p in outline]
    b = [bm.verts.new((depth / 2, p[0], p[1])) for p in outline]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([a[i], a[j], b[j], b[i]])
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=smooth, bevel=bevel, seg=seg, M=M, angle=angle, mat_fn=mat_fn)


def bolt(c, normal, r=0.011, m=None):
    normal = Vector(normal).normalized()
    c = Vector(c)
    return cyl("Bolt", c - normal * 0.004, c + normal * 0.009, r, m or mats["Chrome"], seg=4, caps=(False, True), r1=r * 0.8)


def crom(tab, t):
    """Catmull-Rom through rows (key, v1, v2, ...) sorted by key."""
    keys = [r[0] for r in tab]
    if t <= keys[0]:
        return list(tab[0][1:])
    if t >= keys[-1]:
        return list(tab[-1][1:])
    i = max(k for k in range(len(keys) - 1) if keys[k] <= t)
    p0, p1, p2, p3 = tab[max(i - 1, 0)], tab[i], tab[i + 1], tab[min(i + 2, len(tab) - 1)]
    u = (t - p1[0]) / (p2[0] - p1[0])
    out = []
    for j in range(1, len(p1)):
        a, b, c, d = p0[j], p1[j], p2[j], p3[j]
        out.append(0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u * u + (-a + 3 * b - 3 * c + d) * u ** 3))
    return out


def yt(x, t):
    """NACA 4-digit half thickness (unit chord), closed trailing edge."""
    x = max(0.0, min(1.0, x))
    return 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)


def foil(le, cdir, tdir, chord, t, cut=1.0, N=8, te=0.005):
    """Symmetric airfoil loop from leading-edge point le along cdir; cut < 1 truncates with a blunt rear."""
    le, cdir, tdir = Vector(le), Vector(cdir), Vector(tdir)
    xs = [(1 - math.cos(math.pi * i / N)) / 2 for i in range(N + 1)]
    pts = []
    for i in range(N, -1, -1):
        x = xs[i] * cut
        h = max(yt(x, t) * chord, te if i == N else 0.0)
        pts.append(le + cdir * x * chord + tdir * h)
    for i in range(1, N + 1):
        x = xs[i] * cut
        h = max(yt(x, t) * chord, te if i == N else 0.0)
        pts.append(le + cdir * x * chord - tdir * h)
    return pts


def flap_pts(hinge, cdir, tdir, r, length, te=0.005, arc=5):
    """Control-surface section: round nose of radius r centred on the hinge, tapering to a trailing edge."""
    hinge, cdir, tdir = Vector(hinge), Vector(cdir), Vector(tdir)
    pts = [hinge + cdir * length + tdir * te, hinge + cdir * length * 0.5 + tdir * (r + te) * 0.55]
    for k in range(arc + 1):
        a = math.pi / 2 + math.pi * k / arc
        pts.append(hinge + cdir * math.cos(a) * r + tdir * math.sin(a) * r)
    pts += [hinge + cdir * length * 0.5 - tdir * (r + te) * 0.55, hinge + cdir * length - tdir * te]
    return pts


def collapse(name, group, loc=(0, 0, 0)):
    """Apply modifiers and join a group's parts into one mesh object (origin moved to loc)."""
    if os.environ.get("AV_TRIS"):
        dg = bpy.context.evaluated_depsgraph_get()
        acc = {}
        for o in group.parts:
            k = o.name.split(".")[0]
            acc[k] = acc.get(k, 0) + sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons)
        print("TRIS", name, sorted(acc.items(), key=lambda kv: -kv[1])[:14])
    bpy.ops.object.select_all(action="DESELECT")
    for o in group.parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = group.parts[0]
    bpy.ops.object.convert(target="MESH")
    if len(group.parts) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    bpy.ops.object.material_slot_remove_unused()
    # merge duplicate material slots (same material appearing more than once)
    me = ob.data
    first = {}
    remap = []
    for i, m in enumerate(me.materials):
        first.setdefault(m.name, i)
        remap.append(first[m.name])
    for p in me.polygons:
        p.material_index = remap[p.material_index]
    bpy.ops.object.material_slot_remove_unused()
    loc = Vector(loc)
    if loc.length > 0:
        me.transform(Matrix.Translation(-loc))
        ob.location = loc
    return ob


def join_into(target, obs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()
    return target


def empty(name, loc, size=0.1):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = size
    e.location = Vector(loc)
    bpy.context.collection.objects.link(e)
    return e


def decal(name, target, origin, direction, m, shape, spin=0.0, lift=0.005, up=None, step=0.045):
    """Project flat 2D geometry onto target's surface. shape = list of polygons in (u, v) surface coords."""
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(target, dg)
    hit, nrm, _, _ = bvh.ray_cast(Vector(origin), Vector(direction).normalized())
    if hit is None:
        print("DECAL MISS", name, origin)
        return None
    ref = Vector(up) if up is not None else (Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((0, -1, 0)))
    u = ref.cross(nrm).normalized()
    v = nrm.cross(u).normalized()
    q = Quaternion(nrm, spin)
    u, v = q @ u, q @ v

    def project(p):
        h = bvh.ray_cast(p + nrm * 0.08, -nrm, 0.2)
        if h[0] is None or h[1].dot(nrm) < 0.2:
            return None
        return h[0] + h[1] * lift

    def vert(p):
        q = project(p)
        return bm.verts.new(q) if q is not None else None

    STEP = step
    bm = bmesh.new()

    def tri(a, b, c):
        a, b, c = Vector((*a, 0)), Vector((*b, 0)), Vector((*c, 0))
        n = max(1, math.ceil(max((a - b).length, (b - c).length, (c - a).length) / STEP))
        P = {}
        for i in range(n + 1):
            for j in range(n + 1 - i):
                q = a + (b - a) * (i / n) + (c - a) * (j / n)
                P[i, j] = vert(hit + u * q.x + v * q.y)
        for i in range(n):
            for j in range(n - i):
                face(P[i, j], P[i + 1, j], P[i, j + 1])
                if i + j + 1 < n:
                    face(P[i + 1, j], P[i + 1, j + 1], P[i, j + 1])

    def quad(a, b, c, d):
        a, b, c, d = [Vector((*p, 0)) for p in (a, b, c, d)]
        nu = max(1, math.ceil(max((b - a).length, (c - d).length) / STEP))
        nv = max(1, math.ceil(max((d - a).length, (c - b).length) / STEP))
        P = {}
        for i in range(nu + 1):
            for j in range(nv + 1):
                s_, t_ = i / nu, j / nv
                q = (a * (1 - s_) + b * s_) * (1 - t_) + (d * (1 - s_) + c * s_) * t_
                P[i, j] = vert(hit + u * q.x + v * q.y)
        for i in range(nu):
            for j in range(nv):
                face(P[i, j], P[i + 1, j], P[i + 1, j + 1], P[i, j + 1])

    def face(*vs):
        if any(v_ is None for v_ in vs):
            return
        f = bm.faces.new(vs)
        f.normal_update()
        if f.normal.dot(nrm) < 0:
            f.normal_flip()

    for poly in shape:
        if len(poly) == 3:
            tri(*poly)
        elif len(poly) == 4:
            quad(*poly)
        else:
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            for k in range(len(poly)):
                tri((cx, cy), poly[k], poly[(k + 1) % len(poly)])
    bmesh.ops.delete(bm, geom=[v_ for v_ in bm.verts if not v_.link_faces], context="VERTS")
    return finish_obj(name, bm, m, smooth=False)


def disc_shape(r, seg=16, r_in=0.0, sub=1):
    """Polygons for a projected disc / annulus split into wedges so they hug curves."""
    polys = []
    rads = [r_in + (r - r_in) * k / sub for k in range(sub + 1)]
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        for k in range(sub):
            r0, r1 = rads[k], rads[k + 1]
            if r0 < 1e-6:
                polys.append([(0, 0), (math.cos(a0) * r1, math.sin(a0) * r1), (math.cos(a1) * r1, math.sin(a1) * r1)])
            else:
                polys.append([(math.cos(a0) * r0, math.sin(a0) * r0), (math.cos(a0) * r1, math.sin(a0) * r1),
                              (math.cos(a1) * r1, math.sin(a1) * r1), (math.cos(a1) * r0, math.sin(a1) * r0)])
    return polys


def rect_shape(w, h, nu=1, nv=1, cx=0.0, cy=0.0):
    polys = []
    for i in range(nu):
        for j in range(nv):
            a0, a1 = cx - w / 2 + w * i / nu, cx - w / 2 + w * (i + 1) / nu
            b0, b1 = cy - h / 2 + h * j / nv, cy - h / 2 + h * (j + 1) / nv
            polys.append([(a0, b0), (a1, b0), (a1, b1), (a0, b1)])
    return polys


def blot_shape(sz, asp=1.4, n=14):
    """Organic rust / scuff blot: a wobbly ellipse made of low-frequency sines."""
    ph = [random.uniform(0, 2 * math.pi) for _ in range(3)]
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = sz * (0.82 + 0.12 * math.sin(2 * a + ph[0]) + 0.08 * math.sin(3 * a + ph[1]) + 0.05 * math.sin(5 * a + ph[2]))
        pts.append((math.cos(a) * r * asp, math.sin(a) * r))
    return [pts]


def star_shape(r, r_in, points=5):
    pts = []
    for i in range(points * 2):
        a = math.pi / 2 + math.pi * i / points
        rr = r if i % 2 == 0 else r_in
        pts.append((math.cos(a) * rr, math.sin(a) * rr))
    return [[(0, 0), pts[i], pts[(i + 1) % len(pts)]] for i in range(len(pts))]


# ---------------------------------------------------------------- wheels
def tyre(name, r, width, m, steps=16, knobs=True, M=None):
    """Chunky toy tyre about local X; r = outer radius, width along X."""
    s = r / 0.281
    w = width / 0.224
    prof = [(-0.094, 0.176), (-0.112, 0.214), (-0.110, 0.250), (-0.088, 0.276),
            (0.0, 0.281), (0.088, 0.276), (0.110, 0.250), (0.112, 0.214), (0.094, 0.176)]
    bm = bmesh.new()
    vs = [bm.verts.new((x * w, 0, rr * s)) for x, rr in prof]
    es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(1, 0, 0), dvec=(0, 0, 0),
                   angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.normal_update()
    for f in bm.faces:
        c = f.calc_center_median()
        if abs(c.x) < 0.05 * w and f.normal.dot(Vector((0, c.y, c.z))) < 0:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
            break
    if knobs:
        sel = []
        step = 2 * math.pi / steps
        for f in bm.faces:
            c = f.calc_center_median()
            rr = math.hypot(c.y, c.z)
            k = int(math.floor((math.atan2(c.z, c.y) % (2 * math.pi)) / step))
            side = 1 if c.x > 0 else 0
            if rr > 0.272 * s and (k + side) % 2 == 0:
                sel.append(f)
        ext = bmesh.ops.extrude_discrete_faces(bm, faces=sel)
        for f in ext["faces"]:
            f.normal_update()
            n = f.normal.copy()
            c = f.calc_center_median()
            for v in f.verts:
                v.co = c + (v.co - c) * 0.86 + n * 0.024 * s
    return finish_obj(name, bm, m, smooth=True, M=M)


def wheel(name, c, r, width, M_rubber, hub_m, cap_m, knobs=True, steps=16, flip=False):
    """Tyre + dished hub + cap, axle along X, centred on c. flip mirrors the cap to -X."""
    sgn = -1 if flip else 1
    T = Matrix.Translation(Vector(c))
    tyre(name + "Tyre", r / 1.085 if knobs else r, width, M_rubber, steps=steps, knobs=knobs, M=T)  # r includes the knobs
    hw = width * 0.42
    disc(name + "Dish", Vector(c) + X * sgn * hw * 0.8, X * sgn, r * 0.64, hub_m, seg=14)
    disc(name + "Back", Vector(c) - X * sgn * hw * 0.8, -X * sgn, r * 0.64, hub_m, seg=10)
    cyl(name + "Hub", Vector(c) + X * sgn * hw * 0.7, Vector(c) + X * sgn * (hw + 0.03), r * 0.3, cap_m, seg=10,
        r1=r * 0.22, caps=(False, True))


# ---------------------------------------------------------------- pilot preview (AV_CHECK only)
def add_pilot(seat, char="fox", stand=False):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(CHARS, char + ".glb"))
    new = [o for o in bpy.data.objects if o not in before]
    off = Vector((0, 0, 0 if stand else -0.094))
    for o in new:
        if o.parent is None:
            o.matrix_world = Matrix.Translation(Vector(seat) + off) @ Matrix.Scale(0.55, 4) @ o.matrix_world
    if not stand:
        for o in new:
            base = o.name.split(".")[0]
            if base in ("LegL", "LegR"):
                o.rotation_euler.x += -1.45
            if base in ("ArmL", "ArmR"):
                o.rotation_euler.x += -1.2
    return new


# ---------------------------------------------------------------- export / render
def godot(v):
    return (round(v[0], 3), round(v[2], 3), round(-v[1], 3))


def world_bbox(objs):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        if o.type != "MESH":
            continue
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def export(name, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True)
    tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == "MESH"}
    print("EXPORTED %s.glb" % name, tris, "total", sum(tris.values()))
    lo, hi = world_bbox(objs)
    print("BBOX blender", tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi))
    print("BBOX godot min", (round(lo.x, 3), round(lo.z, 3), round(-hi.y, 3)),
          "max", (round(hi.x, 3), round(hi.z, 3), round(-lo.y, 3)))
    for o in objs:
        print("NODE", o.name, o.type, "godot", godot(o.location))


def render_setup(samples):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scn.render.resolution_x = scn.render.resolution_y = 512
    scn.render.film_transparent = True
    if not scn.world:
        world = bpy.data.worlds.new("Studio")
        scn.world = world
        bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
        bg.inputs["Color"].default_value = (0.62, 0.7, 0.82, 1)
        bg.inputs["Strength"].default_value = 0.55
        bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
        floor = bpy.context.active_object
        floor.name = "ShadowFloor"
        floor.is_shadow_catcher = True


def shoot(path, objs, direction=(2.55, -3.25, 1.75), lens=57, samples=96, fill=0.86, aim_z=None, res=512):
    """Frame the given objects from a direction and render to path."""
    render_setup(samples)
    scn = bpy.context.scene
    scn.render.resolution_x = scn.render.resolution_y = res
    pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        if o.type == "MESH":
            ev = o.evaluated_get(dg)
            pts += [o.matrix_world @ v.co for v in ev.data.vertices]
    lo, hi = Vector(map(min, *pts)), Vector(map(max, *pts))
    ctr = (lo + hi) / 2
    size = (hi - lo).length
    for o in [o for o in bpy.data.objects if o.name.startswith("KeyLight")]:
        bpy.data.objects.remove(o)
    k = max(size / 2.6, 0.6)
    for i, (loc, energy, lsize, col) in enumerate([((3.4, -2.2, 3.8), 320, 2.5, (1, 0.95, 0.88)),
                                                   ((-2.5, -3.5, 1.6), 110, 3.0, (0.8, 0.88, 1.0)),
                                                   ((0.5, 3.5, 2.8), 260, 2.0, (1, 0.95, 0.9))]):
        ld = bpy.data.lights.new("KeyLight%d" % i, "AREA")
        ld.energy = energy * k * k
        ld.size = lsize * k
        ld.color = col
        lt = bpy.data.objects.new("KeyLight%d" % i, ld)
        bpy.context.collection.objects.link(lt)
        lt.location = ctr + Vector(loc) * k
        lt.rotation_euler = (ctr - lt.location).to_track_quat("-Z", "Y").to_euler()
    cam = bpy.data.objects.get("Cam")
    if cam is None:
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        bpy.context.collection.objects.link(cam)
    cam.data.lens = lens
    scn.camera = cam
    d = Vector(direction).normalized()
    rot = (-d).to_track_quat("-Z", "Y")
    R = rot.to_matrix()
    right, upv, fwd = R.col[0], R.col[1], -R.col[2]
    tanh = 18.0 / lens * fill
    target = ctr.copy()
    if aim_z is not None:
        target.z = aim_z
    for _ in range(4):
        # distance so every point fits, then recentre on the projected extents
        dist = 0.0
        for p in pts:
            q = p - target
            x, y, zz = q.dot(right), q.dot(upv), q.dot(fwd)
            dist = max(dist, abs(x) / tanh - zz, abs(y) / tanh - zz)
        campos = target - fwd * dist
        xs = [(p - campos).dot(right) / (p - campos).dot(fwd) for p in pts]
        ys = [(p - campos).dot(upv) / (p - campos).dot(fwd) for p in pts]
        mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        target = target + right * mx * dist + upv * my * dist
    cam.location = campos
    cam.rotation_euler = rot.to_euler()
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


def finish(name, objs, seat, stand=False, thumb_dir=(2.55, -3.25, 1.75), checks=()):
    export(name, objs)
    if os.environ.get("AV_NO_RENDER") == "1":
        return
    shoot(os.path.join(OUT, name + ".png"), objs, direction=thumb_dir)
    if CHECK:
        os.makedirs(CHECK, exist_ok=True)
        pilot = add_pilot(seat, stand=stand)
        views = [("front", (2.55, -3.25, 1.75)), ("back", (-2.2, 3.2, 2.2)), ("side", (4, 0.001, 0.6)),
                 ("top", (0.6, 1.2, 4))] + list(checks)
        for tag, d in views:
            shoot(os.path.join(CHECK, "%s_%s.png" % (name, tag)), objs + pilot, direction=d, samples=24, res=900)


# =================================================================== PLANE
def build_plane():
    C = common_mats()
    RED = mat("Paint", "d83a2c", 0.3, coat=0.6)
    CREAM = mat("Cream", "f5e7c6", 0.34, coat=0.5)
    NAVY = mat("Navy", "23406e", 0.35, coat=0.5)
    YELLOW = mat("Yellow", "f5c22b", 0.35, coat=0.4)
    LEATHER = mat("Leather", "6b3a1f", 0.55, coat=0.15)
    CHROME, METAL, RUBBER, BLACK, GLASS = C["CHROME"], C["METAL"], C["RUBBER"], C["BLACK"], C["GLASS"]

    SEAT = Vector((0.0, 0.02, 0.81))
    HUB = Vector((0.0, -1.07, 0.68))
    # fuselage stations: y, centre z, half-width, half-height, squareness
    FUS = [(-0.80, 0.68, 0.285, 0.285, 2.0),
           (-0.60, 0.68, 0.30, 0.30, 2.3),
           (-0.25, 0.685, 0.305, 0.305, 2.6),
           (0.15, 0.69, 0.29, 0.30, 2.6),
           (0.50, 0.705, 0.205, 0.24, 2.4),
           (0.85, 0.725, 0.115, 0.15, 2.2),
           (1.10, 0.745, 0.06, 0.085, 2.0),
           (1.22, 0.755, 0.03, 0.045, 2.0)]
    SEG = 20

    def fz_top(x, y):
        zc, a, b, n = crom(FUS, y)
        q = min(abs(x) / a, 1.0)
        return zc + b * (1 - q ** n) ** (1 / n)

    # cockpit opening (ellipse in plan)
    CK_Y, CK_L, CK_W = 0.03, 0.31, 0.225

    def in_ck(x, y, k=1.0):
        return ((y - CK_Y) / (CK_L * k)) ** 2 + (x / (CK_W * k)) ** 2 < 1.0

    # ---------------------------------------------------------- body
    new_group()
    ys = [-0.80 + i * 0.065 for i in range(32) if -0.80 + i * 0.065 < 1.215] + [1.22]
    secs = []
    for y in ys:
        zc, a, b, n = crom(FUS, y)
        secs.append(se_pts((0, y, zc), X, Z, a, b, n, SEG))
    secs.append(Vector((0, 1.245, 0.755)))
    bm = loft_bm(secs, cap0=True, cap1=False)
    dead = [f for f in bm.faces if f.calc_center_median().z > 0.82 and in_ck(f.calc_center_median().x, f.calc_center_median().y)]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    fus = finish_obj("Fuselage", bm, RED, smooth=lambda p: len(p.vertices) == 4)

    # coaming (padded leather rim) and the cockpit tub inside
    rim = []
    tub_top = []
    tub_bot = []
    for i in range(28):
        a = 2 * math.pi * i / 28
        x, y = math.cos(a) * CK_W * 1.02, CK_Y + math.sin(a) * CK_L * 1.02
        rim.append(Vector((x, y, fz_top(x, y) + 0.005)))
        tub_top.append(Vector((x * 0.97, y, fz_top(x, y) - 0.02)))
        tub_bot.append(Vector((x * 0.85, CK_Y + (y - CK_Y) * 0.9, 0.5)))
    tube("Coaming", rim, 0.03, LEATHER, sides=6, rad=0, closed=True, up=Z)
    loft("Tub", [tub_top, tub_bot], BLACK, cap0=False, cap1=True, flip=True)
    # seat
    box("Cushion", (0, SEAT.y + 0.02, SEAT.z - 0.03), (0.3, 0.26, 0.06), LEATHER, bevel=0.022, seg=2)
    box("SeatBack", (0, SEAT.y + 0.19, SEAT.z + 0.07), (0.32, 0.06, 0.2), LEATHER, bevel=0.025, seg=2, rot=(-12, 0, 0))
    box("SeatPan", (0, SEAT.y + 0.04, SEAT.z - 0.15), (0.24, 0.24, 0.2), BLACK, bevel=0.0)
    # instrument panel with gauges
    pz = 0.86
    box("Panel", (0, CK_Y - CK_L + 0.06, pz), (0.36, 0.05, 0.13), BLACK, bevel=0.012, seg=1, rot=(-20, 0, 0))
    for gx, gr in ((-0.09, 0.03), (0.0, 0.036), (0.09, 0.03)):
        q = Euler((math.radians(-20), 0, 0)).to_matrix()
        c = Vector((gx, CK_Y - CK_L + 0.06, pz)) + q @ Vector((0, 0.028, 0.005))
        nrm = q @ Vector((0, 1, 0))
        ring("Gauge", c, nrm, gr * 0.78, gr, 0.012, CHROME, seg=10, sides=(0, 1, 2))
        disc("GaugeFace", c + nrm * 0.002, nrm, gr * 0.8, CREAM, seg=12)
    cyl("Stick", (0, SEAT.y - 0.16, 0.56), (0, SEAT.y - 0.2, 0.8), 0.012, BLACK, seg=6)
    blob("StickKnob", (0, SEAT.y - 0.2, 0.81), 0.022, RED, seg=8, rings=5)

    # windscreen: a curved sheet leaning back, chrome frame
    ws_bot, ws_top = [], []
    wy = CK_Y - CK_L - 0.02
    for i in range(9):
        t = -1 + 2 * i / 8
        x = t * 0.21
        yb = wy + 0.06 * t * t
        ws_bot.append(Vector((x, yb, fz_top(x, yb) - 0.01)))
        ws_top.append(Vector((x * 0.9, yb + 0.07, fz_top(x, yb) + 0.17 - 0.03 * t * t)))
    loft("Windscreen", [ws_bot, ws_top], GLASS, cap0=False, cap1=False, wrap=False)
    tube("WsFrame", ws_top, 0.008, CHROME, sides=5, rad=0)
    for e in (0, 8):
        tube("WsPost", [ws_bot[e], ws_top[e]], 0.009, CHROME, sides=5, rad=0)

    # turtle-deck headrest fairing behind the pilot
    hr = []
    for y in (0.36, 0.42, 0.55, 0.72, 0.9):
        zc, a, b, n = crom(FUS, y)
        top = zc + b
        k = {0.36: 0.7, 0.42: 1.0, 0.55: 0.85, 0.72: 0.5, 0.9: 0.12}[y]
        hr.append(se_pts((0, y, top - 0.06), X, Z, 0.11 * min(1.0, k + 0.2), 0.06 + 0.08 * k, 2.2, 14))
    loft("Headrest", hr, RED)

    # cowl: cream ring with a dark recess and a little radial engine
    Mcowl = TRS((0, -0.80, 0.68), (90, 0, 0))
    lathe("Cowl", [(0.283, -0.01), (0.296, 0.05), (0.302, 0.12), (0.29, 0.19), (0.262, 0.225), (0.236, 0.232),
                   (0.218, 0.222), (0.212, 0.19), (0.205, 0.12)], CREAM, seg=SEG, M=Mcowl, cap0=False, cap1=False)
    lathe("CowlBack", [(0.21, 0.125), (0.0, 0.125)], BLACK, seg=SEG, M=Mcowl, cap0=False, cap1=False)
    for i in range(7):
        a = 2 * math.pi * (i + 0.5) / 7
        d = Vector((math.cos(a), 0, math.sin(a)))
        base = Vector((0, -0.93, 0.68))
        cyl("Cylinder", base + d * 0.06, base + d * 0.17, 0.035, METAL, seg=8)
        cyl("CylHead", base + d * 0.165, base + d * 0.19, 0.03, CHROME, seg=8, r1=0.022)
    cyl("Crankcase", (0, -0.92, 0.68), (0, -0.97, 0.68), 0.075, METAL, seg=12)
    # exhaust stubs
    for s in (-1, 1):
        for k in range(3):
            y = -0.72 + k * 0.07
            tube("Exhaust", [(s * 0.27, y, 0.56), (s * 0.33, y + 0.02, 0.52), (s * 0.34, y + 0.07, 0.5)], 0.016, CHROME,
                 sides=5, rad=0.03, n=2)

    # wings (zero dihedral, straight trailing edge; ailerons cut out of the outer trailing edge)
    WZ, TE, AIL_C, AIL_X0, AIL_X1, GAP = 0.47, 0.10, 0.13, 0.62, 1.06, 0.012

    def le_y(x):
        return -0.50 + 0.12 * (abs(x) / 1.28) ** 1.6

    def wing_sec(x, k=1.0, notch=False):
        le = le_y(x)
        chord = (TE - le) * k
        le = le + (TE - le) * (1 - k) * 0.5
        t = 0.16 - 0.04 * abs(x) / 1.28
        cut = 1.0
        if notch:
            cut = (TE - AIL_C - GAP - le) / chord
        return foil((x, le, WZ), Y, Z, chord, t if k > 0.6 else t * 0.8, cut=cut, N=8)

    stations = [(1.30, 0.25), (1.285, 0.6), (1.255, 0.85), (1.2, 0.97), (1.12, 1.0), (AIL_X1 + 0.004, 1.0),
                (AIL_X1, 1.0, True), (AIL_X0, 1.0, True), (AIL_X0 - 0.004, 1.0), (0.3, 1.0)]
    sts = stations + [(-s[0],) + s[1:] for s in reversed(stations)]
    wsecs = [wing_sec(s[0], s[1], len(s) > 2) for s in sts]
    wing = loft("Wing", wsecs, [CREAM, RED], mat_fn=lambda p: 1 if abs(p.center.x) > 1.12 else 0, smooth=True)
    smooth_by_angle(wing, 50)

    def ail(name, sgn):
        xm = (AIL_X0 + AIL_X1) / 2
        chord = TE - le_y(xm)
        cut = (TE - AIL_C - GAP - le_y(xm)) / chord
        r = yt(cut, 0.16 - 0.04 * xm / 1.28) * chord * 0.95
        hy = TE - AIL_C + r
        secs = [flap_pts((sgn * x, hy, WZ), Y, Z, r, TE - hy) for x in (AIL_X0 + GAP, AIL_X1 - GAP)]
        new_group()
        ob = loft(name + "Part", secs, CREAM)
        smooth_by_angle(ob, 50)
        return collapse(name, GROUP, loc=(sgn * xm, hy, WZ))

    # roundels on top of the wings and the fuselage sides
    for s in (-1, 1):
        decal("RoundelO", wing, (s * 0.86, -0.22, 2), (0, 0, -1), NAVY, disc_shape(0.17, 16, 0.0, 1), step=0.09)
        decal("RoundelS", wing, (s * 0.86, -0.22, 2), (0, 0, -1), CREAM, star_shape(0.15, 0.06), lift=0.008, up=-Y, step=0.09)
        decal("RoundelB", wing, (s * 0.86, -0.22, -2), (0, 0, 1), NAVY, disc_shape(0.17, 16, 0.0, 1), step=0.09)
    # cream cheat-line stripe along each side + a racing number disc
    for s in (-1, 1):
        decal("Stripe", fus, (s * 2, -0.18, 0.66), (-s, 0, 0), CREAM, rect_shape(0.85, 0.055, cx=0.0), step=0.06,
              up=Z, spin=0.0)
        decal("Stripe2", fus, (s * 2, -0.18, 0.66), (-s, 0, 0), CREAM, rect_shape(0.55, 0.03, cx=s * 0.22, cy=-0.07), step=0.06)
        decal("NumDisc", fus, (s * 2, 0.32, 0.7), (-s, 0, 0), CREAM, disc_shape(0.095, 14, 0.0, 1), step=0.05)
        decal("NumStar", fus, (s * 2, 0.32, 0.7), (-s, 0, 0), RED, star_shape(0.075, 0.03), lift=0.008, up=Z, step=0.05)

    # tailplane + elevator, fin + rudder
    TZ, TTE = 0.765, 1.07

    def stab_sec(x, k=1.0):
        le = 0.84 + 0.1 * (abs(x) / 0.48) ** 1.5
        chord = (TTE - le) * k
        le = le + (TTE - le) * (1 - k) * 0.5
        return foil((x, le, TZ), Y, Z, chord, 0.13 if k > 0.6 else 0.1, N=6)

    st = [(0.5, 0.3), (0.485, 0.7), (0.45, 1.0), (0.1, 1.0)]
    st = st + [(-a, b) for a, b in reversed(st)]
    tp = loft("Tailplane", [stab_sec(a, b) for a, b in st], [RED, CREAM], mat_fn=lambda p: 0 if abs(p.center.x) > 0.37 else 1)
    smooth_by_angle(tp, 50)

    def fin_sec(z, k=1.0):
        le = 0.80 + 0.22 * ((z - 0.8) / 0.36) ** 1.3 if z > 0.8 else 0.8
        chord = (TTE - le) * k
        le = le + (TTE - le) * (1 - k) * 0.5
        return foil((0, le, z), Y, X, chord, 0.13 if k > 0.6 else 0.1, N=6)

    fs = [(0.74, 1.0), (1.12, 1.0), (1.16, 0.75), (1.175, 0.35)]
    fin = loft("Fin", [fin_sec(a, b) for a, b in fs], [CREAM, RED], mat_fn=lambda p: 1 if p.center.z > 1.05 else 0)
    smooth_by_angle(fin, 50)

    # landing gear: sprung main legs + nose leg, chunky bush tyres (part of Body)
    MW_R, MW_X, MW_Y = 0.17, 0.52, -0.08
    for s in (-1, 1):
        tube("GearLeg", [(s * 0.3, MW_Y, 0.46), (s * 0.44, MW_Y, 0.30), (s * (MW_X - 0.08), MW_Y, MW_R)],
             lambda t: 0.032 - 0.012 * t, METAL, sides=8, rad=0.08, n=3)
        cyl("Axle", (s * (MW_X - 0.1), MW_Y, MW_R), (s * MW_X, MW_Y, MW_R), 0.025, CHROME, seg=8)
        wheel("Main", (s * MW_X, MW_Y, MW_R), MW_R, 0.13, RUBBER, RED, CHROME, flip=s < 0)
    NW_R, NW_Y = 0.115, -0.74
    tube("NoseLeg", [(0, -0.66, 0.42), (0, NW_Y - 0.02, 0.26), (0, NW_Y, NW_R + 0.05)], 0.024, CHROME, sides=8, rad=0.06)
    for s in (-1, 1):
        tube("Fork", [(0, NW_Y, NW_R + 0.07), (s * 0.06, NW_Y, NW_R + 0.06), (s * 0.06, NW_Y, NW_R)], 0.014, METAL,
             sides=6, rad=0.03, n=2)
    wheel("Nose", (0, NW_Y, NW_R), NW_R, 0.08, RUBBER, RED, CHROME, knobs=False, steps=14)
    blob("TailSkid", (0, 1.16, 0.7), (0.025, 0.06, 0.025), BLACK, seg=8, rings=5)

    # a little wear: rust blooms and a scavenged riveted patch
    for o, d, sz, asp, spin in [((0.25, -0.5, 2), (0, 0, -1), 0.05, 1.5, 0.3), ((-2, 0.62, 0.62), (1, 0, 0), 0.045, 1.6, 0.2),
                                ((2, -0.55, 0.45), (-1, 0, 0), 0.04, 1.4, -0.4), ((-0.07, 0.62, 2), (0, 0, -1), 0.035, 1.7, 1.0),
                                ((-0.9, -0.22, 2), (0, 0, -1), 0.04, 1.6, 0.0), ((0.95, -0.3, -2), (0, 0, 1), 0.05, 1.5, 0.5)]:
        tgt = wing if abs(o[0]) < 1.5 and abs(o[2]) == 2 and abs(o[0]) > 0.5 else fus
        decal("Rust", tgt, o, d, C["RUST"], blot_shape(sz, asp), spin=spin)
    pt = decal("Patch", fus, (-2, -0.42, 0.74), (1, 0, 0), METAL, rect_shape(0.2, 0.14), up=Z, spin=0.12, lift=0.006)
    for a, b in ((-0.08, -0.05), (0.08, -0.05), (-0.08, 0.05), (0.08, 0.05)):
        q = Quaternion(X, 0.12)
        p = Vector((-2, -0.42, 0.74)) + q @ Vector((0, a, b))
        hit = BVHTree.FromObject(fus, bpy.context.evaluated_depsgraph_get()).ray_cast(p, X)
        if hit[0] is not None:
            bolt(hit[0], hit[1], r=0.012)

    body = collapse("Body", GROUP)

    # ---------------------------------------------------------- moving parts
    aileron_l = ail("AileronL", 1)
    aileron_r = ail("AileronR", -1)

    new_group()
    EH_Y = TTE + 0.012
    er = 0.024
    xs = [0.47, 0.44, 0.1, -0.1, -0.44, -0.47]
    lens_ = [0.1, 0.13, 0.13, 0.13, 0.13, 0.1]
    esecs = [flap_pts((x, EH_Y + er, TZ), Y, Z, er * (0.6 if abs(x) > 0.46 else 1.0), L) for x, L in zip(xs, lens_)]
    ob = loft("ElevatorPart", esecs, [CREAM, RED], mat_fn=lambda p: 0 if abs(p.center.x) > 0.37 else 1)
    smooth_by_angle(ob, 50)
    elevator = collapse("Elevator", GROUP, loc=(0, EH_Y + er, TZ))

    new_group()
    RH_Y = TTE + 0.012
    rr = 0.022
    zs = [0.80, 1.12, 1.16, 1.18]
    rl = [0.15, 0.15, 0.12, 0.07]
    rsecs = [flap_pts((0, RH_Y + rr, z), Y, X, rr * (0.6 if z > 1.17 else 1.0), L) for z, L in zip(zs, rl)]
    ob = loft("RudderPart", rsecs, [CREAM, RED], mat_fn=lambda p: 1 if p.center.z > 1.05 else 0)
    smooth_by_angle(ob, 50)
    rudder = collapse("Rudder", GROUP, loc=(0, RH_Y + rr, 0.99))

    # propeller: chrome spinner + three twisted blades with yellow tips, in the local XY plane (Godot)
    new_group()
    Msp = TRS(HUB + Vector((0, 0.04, 0)), (90, 0, 0))
    lathe("Spinner", [(0.118, 0.0), (0.116, 0.05), (0.1, 0.1), (0.07, 0.15), (0.035, 0.185), (0.0, 0.2)], RED, seg=16, M=Msp)
    for i in range(3):
        a = 2 * math.pi * i / 3 + math.pi / 2
        rd = Vector((math.cos(a), 0, math.sin(a)))
        tg = Y.cross(rd).normalized()
        secs = []
        for rr_, w, pitch in ((0.07, 0.055, 40), (0.14, 0.095, 32), (0.26, 0.11, 22), (0.38, 0.1, 16), (0.44, 0.08, 14),
                              (0.465, 0.045, 13)):
            th = math.radians(pitch)
            cdir = tg * math.cos(th) - Y * math.sin(th)
            tdir = tg * math.sin(th) + Y * math.cos(th)
            secs.append(foil(HUB + rd * rr_ - cdir * w * 0.4, cdir, tdir, w, 0.2, N=5, te=0.004))
        secs.append(HUB + rd * 0.475)
        ob = loft("Blade", secs, [BLACK, YELLOW], mat_fn=lambda p, rd=rd: 1 if (p.center - HUB).dot(rd) > 0.39 else 0)
        smooth_by_angle(ob, 60)
    prop = collapse("Propeller", GROUP, loc=HUB)

    seat = empty("Seat", SEAT)
    objs = [body, prop, aileron_l, aileron_r, elevator, rudder, seat]
    finish("plane", objs, SEAT)

# =================================================================== HELICOPTER
def sgnpow(v, e):
    return math.copysign(abs(v) ** e, v)


def build_helicopter():
    C = common_mats()
    PAINT = mat("Paint", "ffc400", 0.3, coat=0.35)
    RED = mat("Red", "d42a1e", 0.32, coat=0.55)
    WHITE = mat("White", "f4f1ea", 0.32, coat=0.5)
    TRIM = mat("Trim", "2b2d33", 0.4, coat=0.3)
    INTERIOR = mat("Interior", "3c414b", 0.7)
    SEATM = mat("SeatFabric", "34495e", 0.6, coat=0.1)
    WINDOW = mat("Window", "1d2f45", 0.06, coat=0.8)
    LAMP = mat("Lamp", "fff1c9", 0.05, emit="ffd98a", emit_strength=3.0)
    BEACON = mat("Beacon", "ff3a2a", 0.15, emit="ff2a1a", emit_strength=4.0)
    CHROME, METAL, RUBBER, BLACK, GLASS = C["CHROME"], C["METAL"], C["RUBBER"], C["BLACK"], C["GLASS"]

    SEAT = Vector((0.0, -0.3, 0.47))
    HUB = Vector((0.0, 0.25, 1.37))
    TR_HUB = Vector((0.115, 1.97, 1.04))
    Y_GLASS = 0.06
    HELI = [(-0.95, 0.585, 0.12, 0.13, 2.0),
            (-0.88, 0.605, 0.28, 0.30, 2.2),
            (-0.72, 0.635, 0.37, 0.385, 2.4),
            (-0.45, 0.66, 0.415, 0.42, 2.6),
            (-0.10, 0.67, 0.43, 0.43, 2.8),
            (0.25, 0.68, 0.425, 0.42, 2.8),
            (0.50, 0.70, 0.37, 0.37, 2.6),
            (0.72, 0.76, 0.24, 0.26, 2.3),
            (0.90, 0.80, 0.15, 0.165, 2.1),
            (1.30, 0.835, 0.11, 0.12, 2.0),
            (1.70, 0.865, 0.085, 0.095, 2.0),
            (2.02, 0.885, 0.07, 0.075, 2.0)]
    NU, NL = 10, 14

    def zline(y):
        return 0.60 if y > -0.55 else 0.60 - 0.2 * ((-0.55 - y) / 0.4) ** 1.4

    def hring(y, inset=0.0):
        zc, a, b, n = crom(HELI, y)
        a, b = a - inset, b - inset
        yr = min(y, Y_GLASS)  # behind the canopy keep the same parametrisation so the quads don't twist
        zr, _, br, _ = crom(HELI, yr)
        sv = max(-0.95, min(0.95, (zline(yr) - zr) / (br - inset)))
        tl = math.asin(sgnpow(sv, n / 2))
        ts = [tl + (math.pi - 2 * tl) * k / NU for k in range(NU)] + \
             [math.pi - tl + (math.pi + 2 * tl) * k / NL for k in range(NL)]
        return [Vector((a * sgnpow(math.cos(t), 2 / n), y, zc + b * sgnpow(math.sin(t), 2 / n))) for t in ts]

    ys = [-0.92 + 0.08 * i for i in range(22)]
    ys = [y for y in ys if y < 0.72]
    ys = sorted(set([round(y, 4) for y in ys] + [Y_GLASS]))
    ys += [0.85, 1.0, 1.2, 1.45, 1.7, 1.9, 2.02]
    NOSE = Vector((0, -0.975, 0.58))
    TAIL = Vector((0, 2.06, 0.885))

    def shell(name, inset, keep, m_list, glass_fn, flip=False, sel_y=None):
        bm = bmesh.new()
        sel = [y for y in ys if sel_y is None or sel_y[0] <= y <= sel_y[1]]
        rings = [[bm.verts.new(p) for p in hring(y, inset)] for y in sel]
        n = NU + NL
        if inset == 0:
            pole0, pole1 = bm.verts.new(NOSE), bm.verts.new(TAIL)
            for i in range(n):
                j = (i + 1) % n
                f = bm.faces.new([pole0, rings[0][j], rings[0][i]])
                f.material_index = glass_fn(sel[0], sel[0], i)
                f = bm.faces.new([pole1, rings[-1][i], rings[-1][j]])
        for k, (A, B) in enumerate(zip(rings, rings[1:])):
            for i in range(n):
                j = (i + 1) % n
                if not keep(sel[k], sel[k + 1], i):
                    continue
                f = bm.faces.new([A[i], A[j], B[j], B[i]])
                f.material_index = glass_fn(sel[k], sel[k + 1], i)
        bm.normal_update()
        # outward check: the face at the top of the cabin should point up
        top = max(bm.faces, key=lambda f: f.calc_center_median().z)
        if (top.normal.z < 0) != flip:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        return finish_obj(name, bm, m_list, smooth=True)

    is_glass = lambda y0, y1, i: 1 if (y1 <= Y_GLASS + 1e-6 and i < NU) else 0
    new_group()
    hull = shell("Hull", 0.0, lambda *a: True, [PAINT, GLASS], is_glass)
    shell("Lining", 0.03, lambda y0, y1, i: not is_glass(y0, y1, i), [INTERIOR], lambda *a: 0, flip=True,
          sel_y=(-0.86, 0.5))
    zc, a, b, n = crom(HELI, 0.5)
    loft("Bulkhead", [hring(0.5, 0.03)], INTERIOR, cap0=True, cap1=False, flip=False)

    # canopy frame: sills, rear hoop, centre bar, door hoop
    gys = [y for y in ys if y <= Y_GLASS + 1e-6]
    left = [hring(y)[0] for y in gys]
    right = [hring(y)[NU] for y in gys]
    tube("FrameSill", right[::-1] + [NOSE + Vector((0, 0.005, 0))] + left, 0.024, TRIM, sides=5, rad=0)
    tube("FrameHoop", hring(Y_GLASS)[:NU + 1], 0.03, TRIM, sides=6, rad=0)
    tube("FrameBar", [hring(y)[NU // 2] for y in gys if y > -0.88], 0.018, TRIM, sides=6, rad=0)
    yd = -0.06
    tube("FrameDoor", hring(yd)[:NU + 1], 0.02, TRIM, sides=6, rad=0)

    # cabin floor, pilot seat, console, cyclic, first-aid kit
    box("Floor", (0, -0.2, 0.3), (0.62, 1.2, 0.04), INTERIOR, bevel=0.0)
    box("Cushion", (0, SEAT.y + 0.02, SEAT.z - 0.035), (0.32, 0.28, 0.07), SEATM, bevel=0.025, seg=2)
    box("SeatBack", (0, SEAT.y + 0.19, SEAT.z + 0.13), (0.34, 0.07, 0.3), SEATM, bevel=0.03, seg=2, rot=(-10, 0, 0))
    box("SeatBase", (0, SEAT.y + 0.04, 0.37), (0.24, 0.22, 0.14), METAL, bevel=0.01, seg=1)
    box("Console", (0, -0.74, 0.5), (0.4, 0.16, 0.16), TRIM, bevel=0.03, seg=2, rot=(25, 0, 0))
    for gx in (-0.11, 0.0, 0.11):
        q = Euler((math.radians(25), 0, 0)).to_matrix()
        nrm = q @ Vector((0, 0, 1))
        c = Vector((gx, -0.74, 0.5)) + nrm * 0.082
        ring("Gauge", c, nrm, 0.022, 0.03, 0.01, CHROME, seg=8, sides=(0, 1, 2))
        disc("GaugeFace", c + nrm * 0.001, nrm, 0.024, WHITE, seg=8)
    cyl("Cyclic", (0, SEAT.y - 0.14, 0.32), (0, SEAT.y - 0.22, 0.56), 0.012, BLACK, seg=6)
    blob("Grip", (0, SEAT.y - 0.225, 0.57), (0.02, 0.02, 0.035), BLACK, seg=8, rings=5)
    box("AidKit", (0.0, 0.25, 0.39), (0.26, 0.16, 0.14), WHITE, bevel=0.02, seg=2)
    box("AidCrossA", (0.0, 0.25, 0.462), (0.12, 0.04, 0.006), RED, bevel=0.0)
    box("AidCrossB", (0.0, 0.25, 0.462), (0.04, 0.12, 0.006), RED, bevel=0.0)

    # engine cowling on the roof, intakes, exhausts, mast, beacon
    hsecs = []
    for y, k in ((0.07, 0.55), (0.12, 0.9), (0.22, 1.0), (0.5, 1.0), (0.63, 0.88), (0.71, 0.62), (0.75, 0.3)):
        hsecs.append(se_pts((0, y, 1.04 + 0.03 * (1 - k)), X, Z, 0.25 * k, 0.15 * (0.6 + 0.4 * k), 3.2, 20))
    hsecs.append(Vector((0, 0.765, 1.07)))
    hump = loft("Cowling", hsecs, PAINT)
    smooth_by_angle(hump, 50)
    for s in (-1, 1):
        decal("Intake", hump, (s * 2, 0.2, 1.08), (-s, 0, 0), TRIM, rect_shape(0.14, 0.09), up=Z)
        for k in range(4):
            decal("Louvre", hump, (s * 2, 0.36 + k * 0.05, 1.07), (-s, 0, 0), BLACK, rect_shape(0.018, 0.08),
                  up=Z, lift=0.004)
        tube("ExhaustPipe", [(s * 0.14, 0.6, 1.1), (s * 0.2, 0.72, 1.12), (s * 0.26, 0.8, 1.16)], 0.035, METAL, sides=7,
             rad=0.05, n=2)
        ring("ExhaustTip", Vector((s * 0.262, 0.805, 1.163)), Vector((s * 0.06, 0.8, 0.4)), 0.022, 0.04, 0.04, CHROME, seg=10)
        disc("ExhaustHole", Vector((s * 0.257, 0.795, 1.16)), Vector((s * 0.06, 0.8, 0.4)), 0.024, BLACK, seg=8)
    cyl("Mast", (0, HUB.y, 1.15), (0, HUB.y, HUB.z - 0.05), 0.05, METAL, seg=10)
    cyl("Swash", (0, HUB.y, 1.24), (0, HUB.y, 1.27), 0.095, CHROME, seg=14)
    blob("BeaconLamp", (0, 0.66, 1.17), (0.04, 0.04, 0.035), BEACON, seg=10, rings=5)

    # searchlight under the nose, steps, door, winch hoist (right side)
    cyl("SearchMount", (0, -0.7, 0.28), (0, -0.7, 0.22), 0.03, METAL, seg=8)
    cyl("SearchBody", (0, -0.66, 0.2), (0, -0.8, 0.17), 0.06, CHROME, seg=12, r1=0.07)
    disc("SearchLens", (0, -0.802, 0.169), (0, -1, -0.2), 0.062, LAMP, seg=12)
    for s in (-1, 1):
        decal("Window", hull, (s * 2, 0.3, 0.8), (-s, 0, 0), WINDOW, rect_shape(0.25, 0.15), up=Z)
        for (w, h, cx, cy) in ((0.37, 0.014, 0.0, 0.25), (0.37, 0.014, 0.0, -0.25), (0.014, 0.5, 0.18, 0.0),
                               (0.014, 0.5, -0.18, 0.0)):
            decal("DoorLine", hull, (s * 2, 0.3, 0.67), (-s, 0, 0), TRIM, rect_shape(w, h, cx=cx, cy=cy), step=0.07,
                  up=Z, lift=0.003)
        decal("CrossDisc", hull, (s * 2, 0.86, 0.81), (-s, 0, 0), WHITE, disc_shape(0.095, 14, 0, 1), up=Z, step=0.035)
        decal("CrossA", hull, (s * 2, 0.86, 0.81), (-s, 0, 0), RED, rect_shape(0.12, 0.04), up=Z, lift=0.009, step=0.03)
        decal("CrossB", hull, (s * 2, 0.86, 0.81), (-s, 0, 0), RED, rect_shape(0.04, 0.12), up=Z, lift=0.009, step=0.03)
        decal("Stripe", hull, (s * 2, -0.25, 0.52), (-s, 0, 0), RED, rect_shape(1.25, 0.07, cx=0.12 * s), up=Z, step=0.07)
        tube("DoorRail", [(s * 0.405, 0.04, 1.02), (s * 0.4, 0.55, 1.0)], 0.012, CHROME, sides=5, rad=0)
    hoist = [(-0.3, 0.18, 1.05), (-0.48, 0.18, 1.1), (-0.58, 0.18, 1.06)]
    tube("HoistArm", hoist, 0.03, WHITE, sides=8, rad=0.06, n=2)
    cyl("HoistDrum", (-0.6, 0.18, 1.08), (-0.6, 0.18, 0.98), 0.045, RED, seg=10)
    cyl("Cable", (-0.6, 0.18, 0.98), (-0.6, 0.18, 0.62), 0.006, BLACK, seg=4)
    tube("Hook", [(-0.6, 0.18, 0.62), (-0.6, 0.18, 0.57), (-0.6, 0.15, 0.54), (-0.6, 0.13, 0.57)], 0.011, CHROME, sides=5,
         rad=0.02, n=2)

    # tail: bands, horizontal stabiliser with end plates, fin, ventral fin, gearbox
    for y0, y1, m in ((1.36, 1.44, WHITE), (1.52, 1.6, WHITE), (1.92, 2.02, RED)):
        secs = []
        for y in (y0, y1):
            zc, a, b, n = crom(HELI, y)
            secs.append(se_pts((0, y, zc), X, Z, a + 0.004, b + 0.004, n, 16))
        loft("Band", secs, m, cap0=False, cap1=False)
    zt = crom(HELI, 1.62)[0]
    st = [(0.36, 0.4), (0.33, 1.0), (-0.33, 1.0), (-0.36, 0.4)]
    loft("Stab", [foil((x, 1.56 + 0.06 * (1 - k), zt), Y, Z, 0.16 * k, 0.14, N=5) for x, k in st], RED)
    for s in (-1, 1):
        loft("EndPlate", [foil((s * 0.345, 1.55, z), Y, X, 0.17 * k, 0.12, N=5) for z, k in
                          ((zt - 0.1, 0.5), (zt - 0.07, 1.0), (zt + 0.08, 1.0), (zt + 0.11, 0.5))], RED)

    def fin_sec(z, k=1.0):
        le = 1.80 + 0.2 * max(0.0, (z - 0.85)) / 0.45
        te = 2.08 + 0.06 * max(0.0, (z - 0.85)) / 0.45
        ch = (te - le) * k
        return foil((0, le + (te - le) * (1 - k) / 2, z), Y, X, ch, 0.14, N=6)

    fin = loft("Fin", [fin_sec(z, k) for z, k in ((0.82, 1.0), (1.25, 1.0), (1.3, 0.75), (1.32, 0.35))], [PAINT, RED],
               mat_fn=lambda p: 1 if p.center.z > 1.16 else 0)
    smooth_by_angle(fin, 50)
    loft("Ventral", [foil((0, 1.9 + 0.04 * k, z), Y, X, 0.16 * k, 0.14, N=5) for z, k in ((0.86, 1.0), (0.66, 0.9), (0.62, 0.4))],
         RED)
    blob("GearBox", TR_HUB - X * 0.06, (0.05, 0.07, 0.07), METAL, seg=10, rings=6)
    blob("TailLamp", (0, 2.07, 0.885), 0.025, BEACON, seg=8, rings=4)

    # skids + cross tubes, with step pads
    for s in (-1, 1):
        sk = [(s * 0.44, 0.62, 0.05), (s * 0.44, 0.58, 0.035), (s * 0.44, -0.62, 0.035), (s * 0.44, -0.8, 0.07),
              (s * 0.43, -0.86, 0.17)]
        tube("Skid", sk, 0.035, METAL, sides=7, rad=0.12, n=3)
        for y in (-0.38, 0.32):
            tube("Cross", [(s * 0.44, y, 0.04), (s * 0.43, y, 0.2), (s * 0.3, y, 0.3), (s * 0.1, y, 0.31)], 0.028, METAL,
                 sides=6, rad=0.1, n=2)
        box("Step", (s * 0.44, 0.0, 0.08), (0.06, 0.24, 0.03), BLACK, bevel=0.006, seg=1)
        cyl("StepPost", (s * 0.44, 0.0, 0.04), (s * 0.44, 0.0, 0.08), 0.015, METAL, seg=6)

    # wear
    for o, d, sz, asp, spin in [((2, -0.1, 0.42), (-1, 0, 0), 0.045, 1.6, 0.2), ((-2, 0.55, 0.62), (1, 0, 0), 0.05, 1.4, -0.3),
                                ((2, 1.15, 0.8), (-1, 0, 0), 0.03, 1.8, 0.1), ((-2, 0.05, 0.45), (1, 0, 0), 0.04, 1.5, 0.5)]:
        decal("Rust", hull, o, d, C["RUST"], blot_shape(sz, asp), spin=spin)
    body = collapse("Body", GROUP)

    # main rotor: hub + four blades (grey, red/white tips), origin at the hub
    new_group()
    cyl("HubBody", HUB - Z * 0.05, HUB + Z * 0.04, 0.08, METAL, seg=12)
    blob("HubCap", HUB + Z * 0.04, (0.07, 0.07, 0.05), RED, seg=12, rings=5)
    for i in range(4):
        a = math.pi / 4 + math.pi / 2 * i
        rd = Vector((math.cos(a), math.sin(a), 0))
        tg = Z.cross(rd).normalized()
        box("Grip", HUB + rd * 0.13, (0.18, 0.07, 0.05), CHROME, bevel=0.012, seg=1, rot=(0, 0, math.degrees(a)))
        secs = []
        for r, w in ((0.17, 0.09), (0.26, 0.15), (1.2, 0.15), (1.27, 0.14), (1.3, 0.09)):
            th = math.radians(5)
            cdir = -tg * math.cos(th) - Z * math.sin(th)
            tdir = -tg * math.sin(th) + Z * math.cos(th)
            secs.append(foil(HUB + rd * r - cdir * w * 0.35 - Z * 0.0, cdir, tdir, w, 0.14, N=5))
        ob = loft("Blade", secs, [TRIM, RED, WHITE],
                  mat_fn=lambda p, rd=rd: 2 if 1.08 < (p.center - HUB).dot(rd) < 1.17 else (1 if (p.center - HUB).dot(rd) >= 1.17 else 0))
        smooth_by_angle(ob, 60)
    rotor = collapse("Rotor", GROUP, loc=HUB)

    # tail rotor: three blades in the YZ plane, spins about X
    new_group()
    cyl("TRHub", TR_HUB - X * 0.03, TR_HUB + X * 0.035, 0.035, CHROME, seg=10)
    blob("TRCap", TR_HUB + X * 0.035, (0.02, 0.03, 0.03), RED, seg=8, rings=4)
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.3
        rd = Vector((0, math.cos(a), math.sin(a)))
        tg = X.cross(rd).normalized()
        secs = []
        for r, w in ((0.03, 0.05), (0.06, 0.07), (0.22, 0.07), (0.25, 0.05)):
            th = math.radians(10)
            cdir = tg * math.cos(th) + X * math.sin(th)
            tdir = -tg * math.sin(th) + X * math.cos(th)
            secs.append(foil(TR_HUB + rd * r - cdir * w * 0.4, cdir, tdir, w, 0.16, N=4))
        loft("TRBlade", secs, [WHITE, RED], mat_fn=lambda p, rd=rd: 1 if (p.center - TR_HUB).dot(rd) > 0.17 else 0)
    tail_rotor = collapse("TailRotor", GROUP, loc=TR_HUB)

    seat = empty("Seat", SEAT)
    objs = [body, rotor, tail_rotor, seat]
    finish("helicopter", objs, SEAT)

# =================================================================== ROCKET
def build_rocket():
    C = common_mats()
    HULL = mat("Paint", "f3e9d2", 0.3, coat=0.55)
    RED = mat("Red", "d42a1e", 0.3, coat=0.6)
    TRIM = mat("Trim", "2b2d33", 0.4, coat=0.3)
    INTERIOR = mat("Interior", "3c414b", 0.7)
    SEATM = mat("SeatFabric", "c8402c", 0.5, coat=0.2)
    PORT = mat("Window", "1d3550", 0.05, coat=0.9)
    NOZZLE = mat("Nozzle", "3b3e45", 0.32, metal=1.0)
    GLOW = mat("EngineGlow", "ff9a3c", 0.4, emit="ff7a1a", emit_strength=6.0)
    TIP = mat("TipLight", "7dffb0", 0.2, emit="5dff9a", emit_strength=4.0)
    BUTTON_R = mat("ButtonRed", "ff3b30", 0.3, emit="ff2a1a", emit_strength=1.5)
    BUTTON_G = mat("ButtonGreen", "3bd16f", 0.3, emit="2ad16a", emit_strength=1.5)
    CHROME, METAL, BLACK, GLASS = C["CHROME"], C["METAL"], C["BLACK"], C["GLASS"]

    SEAT = Vector((0.0, 0.04, 1.37))
    FLAME = Vector((0.0, 0.0, 0.11))
    G0, G1 = 1.30, 1.93          # glass cockpit band
    SEG = 32
    FIN_ANG = [90, 210, 330]      # back, front-right, front-left

    new_group()
    # lower hull: skirt -> belly bulge -> shoulder under the cockpit
    lower = [(0.0, 0.34), (0.2, 0.34), (0.3, 0.36), (0.36, 0.42), (0.41, 0.52), (0.445, 0.66), (0.462, 0.82),
             (0.466, 0.98), (0.46, 1.12), (0.45, 1.22), (0.44, G0)]
    hull = lathe("Hull", lower, [HULL, RED], seg=SEG, cap1=False,
                 mat_fn=lambda p: 1 if (p.center.z < 0.45 or 1.13 < p.center.z) else 0)
    lathe("Glass", [(0.44, G0), (0.445, 1.45), (0.442, 1.62), (0.43, 1.78), (0.415, G1)], GLASS, seg=SEG, cap0=False, cap1=False)
    nose = [(0.415, G1), (0.405, 2.0), (0.385, 2.08), (0.35, 2.17), (0.3, 2.27), (0.235, 2.37), (0.165, 2.46),
            (0.095, 2.54), (0.04, 2.6), (0.0, 2.62)]
    lathe("Nose", nose, [RED, HULL], seg=SEG, cap0=False, mat_fn=lambda p: 1 if 2.1 < p.center.z < 2.17 else 0)
    # chrome trim rings at the glass edges + interior floor and ceiling
    for z, r in ((G0, 0.445), (G1, 0.42)):
        tube("TrimRing", [Vector((math.cos(2 * math.pi * i / 32) * r, math.sin(2 * math.pi * i / 32) * r, z)) for i in range(32)],
             0.022, CHROME, sides=6, rad=0, closed=True, up=Z)
    disc("Floor", (0, 0, G0 + 0.005), Z, 0.43, INTERIOR, seg=SEG)
    disc("Ceiling", (0, 0, G1 - 0.005), -Z, 0.41, INTERIOR, seg=SEG)
    # window struts on the diagonals (front stays clear)
    for a in (60, 120, 240, 300):
        d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
        tube("Strut", [d * 0.445 + Z * G0, d * 0.452 + Z * 1.45, d * 0.448 + Z * 1.62, d * 0.435 + Z * 1.78, d * 0.42 + Z * G1],
             0.016, CHROME, sides=6, rad=0)

    # nozzle bell with a glowing throat
    lathe("Nozzle", [(0.15, 0.36), (0.16, 0.3), (0.2, 0.2), (0.255, 0.12), (0.262, 0.105), (0.24, 0.105), (0.19, 0.17),
                     (0.15, 0.24), (0.12, 0.3), (0.0, 0.31)], NOZZLE, seg=24, cap0=False, cap1=False)
    disc("Throat", (0, 0, 0.305), -Z, 0.13, GLOW, seg=16)
    tube("NozzleRing", [Vector((math.cos(2 * math.pi * i / 24) * 0.26, math.sin(2 * math.pi * i / 24) * 0.26, 0.112)) for i in range(24)],
         0.014, CHROME, sides=5, rad=0, closed=True, up=Z)

    # three swept fins, standing on chrome feet
    fin_outline = fillet([(0.40, 1.12), (0.66, 0.82), (0.86, 0.44), (0.98, 0.1), (0.99, 0.02), (0.8, 0.02), (0.74, 0.2),
                          (0.56, 0.38), (0.33, 0.44)], [0, 0.18, 0.2, 0.1, 0.03, 0.03, 0.1, 0.12, 0], n=3, closed=True)
    fin_outline = [(p.x, p.y) for p in fin_outline]
    for a in FIN_ANG:
        M = TRS((0, 0, 0), (0, 0, a - 90))
        extrude("Fin", fin_outline, 0.075, RED, bevel=0.024, seg=2, M=M, angle=40)
        d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
        blob("Foot", d * 0.9 + Z * 0.045, (0.07, 0.07, 0.045), CHROME, seg=12, rings=6, rot=(0, 0, a))
        # fin root fairing strip
        box("FinRoot", d * 0.43 + Z * 0.78, (0.06, 0.06, 0.62), RED, bevel=0.02, seg=2, rot=(0, 0, a))

    # front: two portholes and a riveted hatch, plus a red belly band of rivets
    for z, r in ((0.98, 0.105), (0.68, 0.075)):
        dirn = Vector((0, -1, 0))
        c = Vector((0, -crom([(0.6, 0.445), (0.7, 0.455), (0.85, 0.462), (1.0, 0.466)], z)[0], z))
        ring("Porthole", c + dirn * 0.005, dirn, r * 0.78, r, 0.03, CHROME, seg=16, sides=(0, 1, 2))
        disc("PortGlass", c - dirn * 0.0, dirn, r * 0.8, PORT, seg=16)
        for k in range(8):
            t = 2 * math.pi * (k + 0.5) / 8
            bolt(c + dirn * 0.018 + Vector((math.cos(t), 0, math.sin(t))) * r * 0.9, dirn, r=0.008)
    for k in range(20):
        t = 2 * math.pi * k / 20
        d = Vector((math.cos(t), math.sin(t), 0))
        bolt(d * 0.452 + Z * 1.21, d, r=0.01)
    # hatch on the left side between the fins with a ladder below it
    hd = Vector((math.cos(math.radians(30)), math.sin(math.radians(30)), 0))
    decal("Hatch", hull, hd * 2 + Z * 0.88, -hd, TRIM, rect_shape(0.3, 0.42), up=Z, step=0.05)
    decal("HatchIn", hull, hd * 2 + Z * 0.88, -hd, HULL, rect_shape(0.27, 0.39), up=Z, lift=0.008, step=0.05)
    blob("HatchHandle", hd * 0.47 + Z * 0.88 + hd.cross(Z) * 0.09, (0.012, 0.012, 0.04), CHROME, seg=6, rings=4)
    side = hd.cross(Z).normalized()
    for s in (-1, 1):
        tube("LadderRail", [hd * 0.44 + side * s * 0.085 + Z * 0.72, hd * 0.54 + side * s * 0.085 + Z * 0.66,
                            hd * 0.66 + side * s * 0.085 + Z * 0.016], 0.017, CHROME, sides=6, rad=0.05, n=2)
    for k in range(5):
        t = (k + 0.6) / 5.4
        p = hd * (0.54 + 0.12 * t) + Z * (0.66 * (1 - t))
        tube("Rung", [p - side * 0.085, p + side * 0.085], 0.012, METAL, sides=6, rad=0)

    # cockpit: bucket seat, console with buttons and a joystick
    box("Cushion", (0, SEAT.y + 0.0, SEAT.z - 0.035), (0.3, 0.28, 0.07), SEATM, bevel=0.025, seg=2)
    box("SeatBack", (0, SEAT.y + 0.17, SEAT.z + 0.1), (0.32, 0.07, 0.24), SEATM, bevel=0.03, seg=2, rot=(-10, 0, 0))
    box("SeatBase", (0, SEAT.y + 0.02, (G0 + SEAT.z - 0.07) / 2), (0.2, 0.2, SEAT.z - 0.07 - G0), METAL, bevel=0.0)
    box("Console", (0, -0.3, G0 + 0.09), (0.36, 0.14, 0.18), TRIM, bevel=0.03, seg=2)
    box("ConsoleTop", (0, -0.29, G0 + 0.19), (0.34, 0.16, 0.04), TRIM, bevel=0.012, seg=1, rot=(-20, 0, 0))
    for k, (bx, m) in enumerate(((-0.11, BUTTON_R), (-0.05, BUTTON_G), (0.05, BUTTON_G), (0.11, BUTTON_R))):
        blob("Button", (bx, -0.29, G0 + 0.215), (0.018, 0.018, 0.012), m, seg=8, rings=4)
    cyl("Joystick", (0, -0.2, G0 + 0.12), (0, -0.2, G0 + 0.24), 0.012, BLACK, seg=6)
    blob("JoyKnob", (0, -0.2, G0 + 0.25), 0.026, RED, seg=8, rings=5)

    # antenna + tip light
    cyl("Antenna", (0, 0, 2.6), (0, 0, 2.76), 0.012, CHROME, seg=6)
    blob("TipBall", (0, 0, 2.78), 0.03, TIP, seg=10, rings=6)

    # wear
    for o, d, sz, asp, spin in [((2, -0.3, 0.6), (-1, 0.3, 0), 0.05, 1.5, 0.2), ((-2, 0.2, 1.0), (1, -0.1, 0), 0.04, 1.6, -0.3),
                                ((0.3, 2, 0.75), (-0.15, -1, 0), 0.045, 1.4, 0.6)]:
        decal("Rust", hull, o, d, C["RUST"], blot_shape(sz, asp), spin=spin)
    body = collapse("Body", GROUP)
    seat = empty("Seat", SEAT)
    flame = empty("Flame", FLAME)
    finish("rocket", [body, seat, flame], SEAT, thumb_dir=(2.4, -3.3, 1.2))

# =================================================================== SLEIGH
def spiral2d(c, r0, r1, a0, a1, n):
    """Points (y, z) on a spiral around c from angle a0 to a1 (degrees), radius r0 -> r1."""
    out = []
    for i in range(n + 1):
        t = i / n
        a = math.radians(a0 + (a1 - a0) * t)
        r = r0 + (r1 - r0) * t
        out.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r))
    return out


def ribbon(name, pts2d, x, w, m, outward):
    """Flat strip (filigree) on the plane x = const, facing +/-X."""
    bm = bmesh.new()
    pts = [Vector((0, p[0], p[1])) for p in pts2d]
    rows = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        nrm = Vector((0, -t.z, t.y))
        ww = w * (0.35 + 0.65 * math.sin(math.pi * min(1.0, (i + 0.5) / len(pts))) ** 0.5)
        rows.append([bm.verts.new(Vector((x, p.y, p.z)) + nrm * ww / 2), bm.verts.new(Vector((x, p.y, p.z)) - nrm * ww / 2)])
    for A, B in zip(rows, rows[1:]):
        f = bm.faces.new([A[0], A[1], B[1], B[0]])
        f.normal_update()
        if f.normal.x * outward < 0:
            f.normal_flip()
    return finish_obj(name, bm, m, smooth=False)


def build_sleigh():
    C = common_mats()
    RED = mat("Paint", "c8201c", 0.28, coat=0.65)
    REDIN = mat("PaintInner", "8e1614", 0.45, coat=0.3)
    GOLD = mat("Gold", "f2c14e", 0.22, metal=1.0)
    VELVET = mat("Velvet", "2f6b3f", 0.75, coat=0.05)
    SACK = mat("Sack", "b98a55", 0.9)
    ROPE = mat("Rope", "e9d3a3", 0.85)
    LEATHER = mat("Leather", "5a3420", 0.55, coat=0.15)
    LANTERN = mat("Lantern", "fff1c9", 0.05, emit="ffcf6b", emit_strength=4.0)
    GIFT = [mat("GiftBlue", "2f7fd6", 0.3, coat=0.5), mat("GiftGreen", "2fa65a", 0.3, coat=0.5),
            mat("GiftPurple", "8a4fd0", 0.3, coat=0.5), mat("GiftWhite", "f4f1ea", 0.3, coat=0.5)]
    FUR = mat("Fur", "8b5a35", 0.8)
    FURLIGHT = mat("FurLight", "e3c9a0", 0.8)
    HOOF = mat("Hoof", "2b211b", 0.5, coat=0.3)
    ANTLER = mat("Antler", "dcc6a0", 0.6)
    EYE = mat("Eye", "0d0d0f", 0.1, coat=1.0)
    WHITE = mat("White", "ffffff", 0.3)
    NOSEB = mat("Nose", "151517", 0.25, coat=0.8)
    NOSEGLOW = mat("NoseGlow", "ff2214", 0.2, emit="ff1a0a", emit_strength=2.5)
    SEAT = Vector((0.0, 0.04, 0.46))
    PX = 0.37  # side panel centre |x|
    RX = 0.33  # runner |x|

    new_group()
    # side panels: high scrolled back, low middle, swan-neck front
    side = [(-0.42, 0.22), (0.88, 0.22), (1.0, 0.32), (1.03, 0.62), (1.0, 0.86), (0.92, 0.96), (0.82, 0.95), (0.76, 0.85),
            (0.6, 0.74), (0.32, 0.71), (0.2, 0.6), (-0.12, 0.58), (-0.3, 0.66), (-0.5, 0.84), (-0.62, 0.93), (-0.71, 0.9),
            (-0.69, 0.78), (-0.57, 0.6), (-0.5, 0.38)]
    rads = [0.08, 0.09, 0.1, 0.12, 0.1, 0.06, 0.05, 0.08, 0.1, 0.1, 0.1, 0.12, 0.12, 0.1, 0.05, 0.05, 0.1, 0.12, 0.1]
    outline = [(p.x, p.y) for p in fillet(side, rads, n=2, closed=True)]
    for sx in (-1, 1):
        extrude("SidePanel", outline, 0.06, [RED, REDIN], bevel=0.018, seg=1, M=TRS((sx * PX, 0, 0)), angle=40,
                mat_fn=lambda p, sx=sx: 1 if p.normal.x * sx < -0.5 else 0)
    # front wall and rear wall (curved plates), floor
    def plate(name, centre, w, m, thick=0.05):
        cl = [Vector((0, a, b)) for a, b in centre]
        ptsA, ptsB = [], []
        for i, p in enumerate(cl):
            a, b = cl[max(i - 1, 0)], cl[min(i + 1, len(cl) - 1)]
            t = (b - a).normalized()
            nrm = Vector((0, -t.z, t.y))
            ptsA.append((p + nrm * thick / 2).yz)
            ptsB.append((p - nrm * thick / 2).yz)
        return extrude(name, [tuple(p) for p in ptsA + ptsB[::-1]], w, m, bevel=0.012, seg=1, angle=40)
    fw = plate("FrontWall", fillet([(-0.47, 0.24), (-0.52, 0.45), (-0.58, 0.66), (-0.65, 0.86)], 0.1, n=2), 0.7, RED)
    decal("FrontStar", fw, (0, -2, 0.56), (0, 1, 0), GOLD, star_shape(0.1, 0.042), up=Z, step=0.2)
    for sx in (-1, 1):
        decal("FrontDot", fw, (sx * 0.2, -2, 0.56), (0, 1, 0), GOLD, disc_shape(0.03, 8), up=Z, step=0.2)
    plate("RearWall", fillet([(0.95, 0.24), (0.99, 0.46), (0.98, 0.7), (0.9, 0.9)], 0.1, n=2), 0.7, RED)
    box("Floor", (0, 0.23, 0.245), (0.7, 1.4, 0.05), REDIN, bevel=0.0)
    # velvet bench + tufted back
    box("Cushion", (0, SEAT.y, SEAT.z - 0.05), (0.66, 0.36, 0.1), VELVET, bevel=0.035, seg=1)
    box("BenchBase", (0, SEAT.y, 0.33), (0.66, 0.32, 0.16), REDIN, bevel=0.0)
    box("SeatBack", (0, 0.31, 0.62), (0.68, 0.09, 0.36), VELVET, bevel=0.035, seg=1, rot=(-8, 0, 0))
    tube("BackRail", [(-0.36, 0.3 + 0.02, 0.81), (0.36, 0.3 + 0.02, 0.81)], 0.02, GOLD, sides=6, rad=0)

    # gold trim along the top edge of each side, ending in curls front and back
    top = [(0.84, 0.95), (0.76, 0.85), (0.6, 0.74), (0.32, 0.71), (0.2, 0.6), (-0.12, 0.58), (-0.3, 0.66), (-0.5, 0.84), (-0.62, 0.93)]
    toprad = [0.0, 0.08, 0.1, 0.1, 0.1, 0.12, 0.12, 0.1, 0.0]
    trim = [Vector((0, p.x, p.y)) for p in fillet(top, toprad, n=1)]
    rear_curl = spiral2d((0.92, 0.88), 0.085, 0.025, 120, -200, 7)
    front_curl = spiral2d((-0.645, 0.85), 0.085, 0.025, 60, 380, 7)
    for sx in (-1, 1):
        x = sx * (PX + 0.035)
        path = [Vector((x, a, b)) for a, b in rear_curl[::-1]] + [Vector((x, p.y, p.z)) for p in trim] + \
               [Vector((x, a, b)) for a, b in front_curl]
        tube("Trim", path, 0.017, GOLD, sides=5, rad=0)
        tube("BottomTrim", [(x, 0.9, 0.235), (x, -0.45, 0.235)], 0.014, GOLD, sides=5, rad=0)
        # filigree swirls and a gold star on the outside of each panel
        xo = sx * (PX + 0.031)
        ribbon("Swirl", spiral2d((0.62, 0.45), 0.13, 0.02, 200, -160, 22), xo, 0.024, GOLD, sx)
        ribbon("Swirl", spiral2d((-0.3, 0.42), 0.11, 0.02, -20, 340, 20), xo, 0.022, GOLD, sx)
        bm = bmesh.new()
        st = star_shape(0.085, 0.036)
        for tri_ in st:
            vs = [bm.verts.new((xo + sx * 0.001, 0.17 + a * sx, 0.41 + b)) for a, b in tri_]
            f = bm.faces.new(vs)
            f.normal_update()
            if f.normal.x * sx < 0:
                f.normal_flip()
        finish_obj("Star", bm, GOLD, smooth=False)

    # curly runners on gold struts
    run = [(1.0, 0.09), (0.93, 0.04), (0.8, 0.03)] + spiral2d((-0.7, 0.33), 0.30, 0.06, -90, -500, 22)
    run = [(1.02, 0.12), (0.96, 0.06)] + [(0.85, 0.03)] + [(y, z) for y, z in run[3:]]
    for sx in (-1, 1):
        x = sx * RX
        path = [Vector((x, a, b)) for a, b in run]
        tube("Runner", path, lambda t: 0.026 if t < 0.7 else 0.026 - 0.012 * (t - 0.7) / 0.3, GOLD, sides=5, rad=0)
        blob("RunnerEnd", path[-1], 0.03, GOLD, seg=6, rings=4)
        for y in (-0.28, 0.3, 0.8):
            tube("Strut", [(x, y, 0.04), (x, y, 0.23)], 0.02, GOLD, sides=5, rad=0, caps=False)
        tube("Brace", [(x, -0.28, 0.06), (x, 0.3, 0.2), (x, 0.8, 0.06)], 0.012, GOLD, sides=4, rad=0.2, n=3)

    # Santa's sack with presents poking out, and a couple on the floor
    random.seed(11)
    bm = bmesh.new()
    prof = [(0.0, 0.0), (0.2, 0.01), (0.27, 0.08), (0.29, 0.2), (0.27, 0.34), (0.2, 0.45), (0.1, 0.52), (0.075, 0.55), (0.1, 0.6),
            (0.13, 0.64)]
    sack_c = Vector((-0.05, 0.62, 0.27))
    rings_ = []
    for r, h in prof:
        ring_ = []
        for i in range(12):
            a = 2 * math.pi * i / 12
            k = 1 + (0.08 * math.sin(3 * a + h * 9) + 0.05 * math.sin(5 * a)) * (1 if 0.05 < h < 0.5 else 0.3)
            ring_.append(bm.verts.new(sack_c + Vector((math.cos(a) * r * k * 1.05, math.sin(a) * r * k * 0.9, h + 0.02 * math.sin(2 * a)))))
        rings_.append(ring_)
    for A, B in zip(rings_, rings_[1:]):
        for i in range(12):
            j = (i + 1) % 12
            bm.faces.new([A[i], A[j], B[j], B[i]])
    bm.faces.new(rings_[0][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        if len(f.verts) > 4:
            bmesh.ops.reverse_faces(bm, faces=[f]) if f.normal.z > 0 else None
    sack = finish_obj("Sack", bm, SACK, smooth=lambda p: len(p.vertices) == 4)
    smooth_by_angle(sack, 60)
    tube("SackTie", [sack_c + Vector((math.cos(2 * math.pi * i / 12) * 0.085, math.sin(2 * math.pi * i / 12) * 0.075, 0.555))
                     for i in range(8)], 0.016, ROPE, sides=4, rad=0, closed=True, up=Z)
    disc("SackMouth", sack_c + Z * 0.62, Z, 0.11, LEATHER, seg=12)
    gifts = [((-0.08, 0.6, 0.86), (0.13, 0.13, 0.13), (12, -10, 20), 0, RED),
             ((0.04, 0.66, 0.84), (0.11, 0.11, 0.15), (-15, 8, -25), 1, GOLD),
             ((-0.14, 0.67, 0.83), (0.1, 0.1, 0.1), (5, 20, 40), 2, VELVET),
             ((0.22, 0.75, 0.33), (0.16, 0.16, 0.14), (0, 0, 15), 3, RED),
             ((0.22, 0.55, 0.32), (0.12, 0.12, 0.12), (0, 0, -20), 0, GOLD)]
    for gk, (c, sz, rot, gi, ribbon_m) in enumerate(gifts):
        box("Gift", c, sz, GIFT[gi], bevel=0.012, seg=1, rot=rot)
        box("RibbonA", c, (sz[0] + 0.006, sz[1] * 0.22, sz[2] + 0.006), ribbon_m, bevel=0.0, rot=rot)
        box("RibbonB", c, (sz[0] * 0.22, sz[1] + 0.006, sz[2] + 0.006), ribbon_m, bevel=0.0, rot=rot)
        q = Euler([math.radians(a) for a in rot]).to_matrix()
        topc = Vector(c) + q @ Vector((0, 0, sz[2] / 2 + 0.012))
        for k in ((-1, 1) if gk < 3 else ()):
            blob("Bow", topc + q @ Vector((k * 0.025, 0, 0)), (0.026, 0.012, 0.016), ribbon_m, seg=6, rings=3,
                 rot=(math.degrees(0.0) + rot[0], rot[1] + k * 20, rot[2]))

    # lantern on a curly hook at the front left
    tube("LanternHook", [(0.41, -0.6, 0.86), (0.47, -0.62, 0.93), (0.52, -0.66, 0.9), (0.52, -0.66, 0.84)], 0.01, GOLD, sides=4,
         rad=0.03, n=2)
    box("LanternGlass", (0.52, -0.66, 0.77), (0.07, 0.07, 0.09), LANTERN, bevel=0.0)
    box("LanternTop", (0.52, -0.66, 0.83), (0.09, 0.09, 0.025), GOLD, bevel=0.008, seg=1)
    box("LanternBase", (0.52, -0.66, 0.715), (0.09, 0.09, 0.025), GOLD, bevel=0.008, seg=1)
    for a, b in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        cyl("LanternPost", (0.52 + a * 0.037, -0.66 + b * 0.037, 0.72), (0.52 + a * 0.037, -0.66 + b * 0.037, 0.82), 0.006, GOLD,
            seg=4, caps=(False, False))
    tube("DashRail", [(-0.33, -0.66, 0.9), (0.33, -0.66, 0.9)], 0.018, GOLD, sides=6, rad=0)
    sleigh = collapse("Body", GROUP)

    # ---------------------------------------------------------- reindeer team
    DY = -1.62
    team = []

    def deer(n, dx, rudolph):
        D = Vector((dx, DY, 0.0))
        BC = D + Vector((0, 0, 0.5))
        objs = []
        # body (two-tone: cream chest and belly), collar with bells, girth strap, white tail tuft
        new_group()
        BODY = [(-0.3, 0.04, 0.05, 0.06), (-0.26, 0.03, 0.105, 0.125), (-0.17, 0.01, 0.135, 0.155), (-0.04, 0.0, 0.13, 0.145),
                (0.1, 0.01, 0.13, 0.14), (0.21, 0.03, 0.125, 0.135), (0.28, 0.045, 0.085, 0.095), (0.31, 0.05, 0.03, 0.035)]
        secs = []
        for yy, zz, a, b in BODY:
            secs.append(se_pts(BC + Vector((0, yy, zz)), X, Z, a * 1.08, b, 2.2, 12, phase=0.5))
        secs = [BC + Vector((0, -0.315, 0.04))] + secs + [BC + Vector((0, 0.325, 0.05))]
        ob = loft("DeerTorso", secs, [FUR, FURLIGHT],
                  mat_fn=lambda p: 1 if p.center.z < BC.z - 0.09 else 0)
        blob("ChestFluff", BC + Vector((0, -0.25, -0.02)), (0.1, 0.07, 0.11), FURLIGHT, seg=8, rings=5, rot=(25, 0, 0))
        cc = BC + Vector((0, -0.2, 0.012))
        col = [se_pts(cc + Vector((0, d, 0)), X, Z, 0.153, 0.162, 2.2, 12, phase=0.5) for d in (-0.03, 0.03)]
        loft("Collar", col, RED, cap0=False, cap1=False)
        for k in range(3):
            a = math.radians(-90 + (k - 1) * 34)
            blob("Bell", cc + Vector((math.cos(a) * 0.15, -0.035, math.sin(a) * 0.17)), 0.027, GOLD, seg=7, rings=4)
        gc = BC + Vector((0, 0.03, 0.0))
        girth = [se_pts(gc + Vector((0, d, 0)), X, Z, 0.147, 0.151, 2.2, 12, phase=0.5) for d in (-0.025, 0.025)]
        loft("Girth", girth, RED, cap0=False, cap1=False)
        box("Pad", BC + Vector((0, 0.03, 0.15)), (0.2, 0.14, 0.02), RED, bevel=0.008, seg=1)
        blob("Tail", BC + Vector((0, 0.31, 0.12)), (0.04, 0.035, 0.05), WHITE, seg=6, rings=4, rot=(-30, 0, 0))
        objs.append(collapse("Deer%dBody" % n, GROUP, loc=BC))
        # legs: origin at the shoulder / hip joint, hooves on the ground
        for code, sx, front in (("FL", 1, True), ("FR", -1, True), ("BL", 1, False), ("BR", -1, False)):
            new_group()
            J = D + Vector((sx * 0.072, -0.19 if front else 0.19, 0.46))
            h = J.z
            if front:
                path = [J + Vector((0, 0, 0.06)), J, J + Vector((0, 0.015, -0.2)), J + Vector((0, -0.01, -0.33)),
                        J + Vector((0, 0, -h + 0.05))]
            else:
                path = [J + Vector((0, 0, 0.06)), J, J + Vector((0, -0.04, -0.15)), J + Vector((0, 0.035, -0.28)),
                        J + Vector((0, 0.0, -h + 0.05))]
            tube("Leg", path, lambda t: 0.068 - 0.036 * min(1.0, t / 0.45) - 0.004 * t, FUR, sides=5, rad=0.05, n=1)
            blob("Cuff", (J.x, path[-1].y, 0.075), (0.038, 0.038, 0.03), FURLIGHT, seg=6, rings=3)
            lathe("Hoof", [(0.036, 0.0), (0.038, 0.03), (0.03, 0.058)], HOOF, seg=6, cap1=False,
                  M=Matrix.Translation((J.x, path[-1].y, 0.0)))
            objs.append(collapse("Deer%dLeg%s" % (n, code), GROUP, loc=J))
        # head: origin at the neck joint
        new_group()
        J = BC + Vector((0, -0.21, 0.1))
        H = J + Vector((0, -0.17, 0.28))
        tube("Neck", [J + Vector((0, 0.03, -0.05)), J + Vector((0, -0.06, 0.12)), H + Vector((0, 0.04, -0.03))],
             lambda t: 0.085 - 0.03 * t, FUR, sides=8, rad=0.06, n=2)
        blob("Skull", H, (0.085, 0.095, 0.08), FUR, seg=10, rings=6)
        blob("Muzzle", H + Vector((0, -0.095, -0.035)), (0.06, 0.08, 0.054), FURLIGHT, seg=10, rings=5)
        if rudolph:
            blob("Nose", H + Vector((0, -0.178, -0.022)), 0.044, NOSEGLOW, seg=10, rings=6)
        else:
            blob("Nose", H + Vector((0, -0.17, -0.02)), (0.032, 0.026, 0.024), NOSEB, seg=8, rings=4)
        for sx in (-1, 1):
            blob("Eye", H + Vector((sx * 0.06, -0.05, 0.025)), 0.022, EYE, seg=7, rings=4)
            blob("Glint", H + Vector((sx * 0.072, -0.062, 0.036)), 0.0075, WHITE, seg=4, rings=2)
            blob("Ear", H + Vector((sx * 0.1, 0.03, 0.05)), (0.055, 0.02, 0.028), FUR, seg=6, rings=4, rot=(0, -sx * 25, sx * 15))
            blob("EarIn", H + Vector((sx * 0.103, 0.017, 0.052)), (0.04, 0.006, 0.018), FURLIGHT, seg=5, rings=3,
                 rot=(0, -sx * 25, sx * 15))
            A = [H + Vector((sx * 0.04, 0.02, 0.06)), H + Vector((sx * 0.085, 0.04, 0.16)), H + Vector((sx * 0.15, 0.08, 0.24)),
                 H + Vector((sx * 0.17, 0.16, 0.31))]
            tube("Antler", A, lambda t: 0.021 - 0.009 * t, ANTLER, sides=5, rad=0.05, n=1)
            tube("Tine", [A[1] + Vector((0, 0.0, 0.0)), A[1] + Vector((sx * 0.015, -0.07, 0.09))], lambda t: 0.014 - 0.006 * t, ANTLER,
                 sides=5, rad=0)
            tube("Tine", [A[2], A[2] + Vector((sx * 0.06, -0.05, 0.08))], lambda t: 0.013 - 0.005 * t, ANTLER, sides=5, rad=0)
        bridle = [H + Vector((0, -0.08, -0.035)) + Vector((math.cos(2 * math.pi * i / 10) * 0.064, 0, math.sin(2 * math.pi * i / 10) * 0.058))
                  for i in range(10)]
        tube("Bridle", bridle, 0.009, RED, sides=3, rad=0, closed=True, up=Y)
        objs.append(collapse("Deer%dHead" % n, GROUP, loc=J))
        return objs

    deer_objs = deer(1, 0.25, True) + deer(2, -0.25, False)

    # harness: shaft and yoke, leather traces from the collars, reins to the dash
    new_group()
    tube("Shaft", [(0, -0.47, 0.3), (0, -1.0, 0.36), (0, -1.95, 0.44)], 0.024, RED, sides=6, rad=0.3, n=3)
    blob("ShaftTip", (0, -1.97, 0.445), 0.034, GOLD, seg=6, rings=4)
    tube("Yoke", [(-0.44, -1.8, 0.45), (0.44, -1.8, 0.45)], 0.02, RED, sides=6, rad=0)
    for sx in (-1, 1):
        blob("YokeEnd", (sx * 0.45, -1.8, 0.45), 0.026, GOLD, seg=6, rings=4)
        for dx in (0.25, -0.25):
            for k in (-1, 1):
                x0 = dx + k * 0.15
                if (dx > 0) != (sx > 0):
                    continue
                tube("Trace", [(x0, DY - 0.2, 0.5), (x0 * 0.9 + (0.06 if x0 > 0 else -0.06), -1.0, 0.36), (sx * 0.34, -0.5, 0.33)],
                     0.011, LEATHER, sides=4, rad=0.3, n=3)
        tube("Rein", [(sx * 0.25, DY - 0.22, 0.66), (sx * 0.2, -1.1, 0.8), (sx * 0.16, -0.66, 0.9)], 0.0065, RED, sides=4, rad=0.3, n=3)
    harness = collapse("Harness", GROUP)
    body = join_into(sleigh, [harness])
    seat = empty("Seat", SEAT)
    sparkles = empty("Sparkles", (0, 0.1, 0.0))
    finish("sleigh", [body] + deer_objs + [seat, sparkles], SEAT, thumb_dir=(2.9, -2.9, 1.7))

# =================================================================== HOVERBOARD
def build_hoverboard():
    C = common_mats()
    PINK = mat("Paint", "ff3e9a", 0.3, coat=0.65)
    GRIP = mat("Grip", "24252b", 0.85)
    YELLOW = mat("Yellow", "ffd21f", 0.3, coat=0.5)
    MAGRED = mat("MagnetRed", "e0261b", 0.3, coat=0.6)
    GLOW = mat("HoverGlow", "8ff6ff", 0.2, emit="3ee8ff", emit_strength=5.0)
    LAMP = mat("Lamp", "fff1c9", 0.05, emit="ffd98a", emit_strength=3.0)
    CHROME, METAL, BLACK = C["CHROME"], C["METAL"], C["BLACK"]

    DECK = [(-0.40, 0.232, 0.05, 0.014), (-0.38, 0.222, 0.105, 0.02), (-0.33, 0.2, 0.14, 0.025), (-0.25, 0.178, 0.155, 0.027),
            (0.0, 0.17, 0.16, 0.027), (0.25, 0.178, 0.155, 0.027), (0.33, 0.198, 0.14, 0.025), (0.38, 0.218, 0.105, 0.02),
            (0.40, 0.228, 0.05, 0.014)]
    top_z = 0.17 + 0.027
    SEAT = Vector((0.0, 0.0, top_z))
    new_group()
    ys = [-0.40 + 0.8 * i / 26 for i in range(27)]
    secs = [Vector((0, -0.412, 0.233))]
    for y in ys:
        zc, a, b = crom(DECK, y)
        secs.append(se_pts((0, y, zc), X, Z, a, b, 3.2, 24))
    secs.append(Vector((0, 0.412, 0.229)))

    def deck_mat(p):
        n = p.normal
        if n.z > 0.75 and abs(p.center.y) < 0.35 and abs(p.center.x) < 0.128:
            return 1
        if n.z > 0.2:
            return 0
        if n.z > -0.45:
            return 2
        return 0
    deck = loft("Deck", secs, [PINK, GRIP, YELLOW], mat_fn=deck_mat)
    smooth_by_angle(deck, 40)
    # top graphics: a yellow lightning bolt and a red horseshoe magnet
    zap = [[(-0.01, 0.14), (0.055, 0.14), (0.022, 0.02), (-0.045, 0.02)],
           [(-0.02, 0.035), (0.06, 0.035), (-0.035, -0.15)]]
    decal("Zap", deck, (0, 0.17, 1), (0, 0, -1), YELLOW, zap, up=-Y, step=0.3)
    mag = []
    for i in range(8):
        a0, a1 = math.pi * i / 8, math.pi * (i + 1) / 8
        mag.append([(math.cos(a0) * 0.05, math.sin(a0) * 0.05), (math.cos(a0) * 0.09, math.sin(a0) * 0.09),
                    (math.cos(a1) * 0.09, math.sin(a1) * 0.09), (math.cos(a1) * 0.05, math.sin(a1) * 0.05)])
    for sx in (-1, 1):
        mag.append([(sx * 0.05, 0), (sx * 0.09, 0), (sx * 0.09, -0.04), (sx * 0.05, -0.04)][:: 1 if sx > 0 else -1])
    decal("Magnet", deck, (0, -0.17, 1), (0, 0, -1), MAGRED, mag, up=Y, step=0.3)
    tips = [[(sx * 0.05, -0.04), (sx * 0.09, -0.04), (sx * 0.09, -0.07), (sx * 0.05, -0.07)][:: 1 if sx > 0 else -1] for sx in (-1, 1)]
    decal("MagnetTips", deck, (0, -0.17, 1), (0, 0, -1), CHROME, tips, up=Y, step=0.3)
    # chrome bumper rails on nose and tail
    for sgn in (-1, 1):
        pts = []
        for i in range(9):
            a = math.pi * (0.12 + 0.76 * i / 8)
            y0 = sgn * 0.33
            pts.append(Vector((math.cos(a) * 0.15, y0 + sgn * math.sin(a) * 0.085, crom(DECK, y0 + sgn * math.sin(a) * 0.085)[0])))
        tube("Bumper", pts, 0.013, CHROME, sides=6, rad=0)
    # hover pads: chrome housings with a glowing ring and red magnet band; glow discs underneath
    for y in (-0.24, 0.24):
        lathe("Pad", [(0.0, 0.02), (0.064, 0.02), (0.074, 0.0), (0.094, 0.004), (0.103, 0.028), (0.105, 0.05), (0.106, 0.08),
                      (0.1, 0.11), (0.085, 0.14), (0.0, 0.15)], [CHROME, GLOW, MAGRED], seg=20, M=Matrix.Translation((0, y, 0)),
              mat_fn=lambda p: 1 if (0.022 < p.center.z < 0.045 or p.center.z < 0.019) else (2 if 0.06 < p.center.z < 0.105 else 0))
        disc("PadGlow", (0, y, 0.018), -Z, 0.066, GLOW, seg=16)
        for k in range(6):
            a = 2 * math.pi * (k + 0.5) / 6
            bolt(Vector((math.cos(a) * 0.098, y + math.sin(a) * 0.098, 0.116)), Vector((math.cos(a), math.sin(a), 0.6)), r=0.009)
    # glow strip under the deck + tail fins + nose lamp
    box("UnderGlow", (0, 0, 0.142), (0.05, 0.26, 0.012), GLOW, bevel=0.0)
    for sx in (-1, 1):
        fo = [(p_.x, p_.y) for p_ in fillet([(0.2, 0.17), (0.33, 0.18), (0.37, 0.1), (0.29, 0.1)], [0, 0.02, 0.02, 0.02], n=2, closed=True)]
        extrude("Fin", fo, 0.014, YELLOW, bevel=0.004, seg=1, M=TRS((sx * 0.075, 0, 0.15), (0, sx * 12, 0)) @ TRS((0, 0, -0.15)))
    blob("NoseLamp", (0, -0.405, 0.226), (0.03, 0.012, 0.012), LAMP, seg=8, rings=4)
    for o, d, sz in [((0.12, 0.05, -1), (0, 0, 1), 0.035), ((-0.13, -0.2, -1), (0, 0, 1), 0.03)]:
        decal("Scuff", deck, o, d, C["RUST"], blot_shape(sz, 1.6), step=0.2)
    body = collapse("Body", GROUP)
    seat = empty("Seat", SEAT)
    fx = empty("HoverFX", (0, 0, 0.0))
    finish("hoverboard", [body, seat, fx], SEAT, stand=True, thumb_dir=(2.2, -3.0, 2.2))


BUILDERS = {"sleigh": build_sleigh, "plane": build_plane, "helicopter": build_helicopter, "rocket": build_rocket, "hoverboard": build_hoverboard}


def reset():
    global mats
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {}
    random.seed(7)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for name in (argv or list(BUILDERS)):
        reset()
        BUILDERS[name]()
