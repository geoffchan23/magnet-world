# Tower crane + wrecking ball for the "destroy" feature.
# Run: blender --background --python art/src/crane.py
# Exports assets/crane/crane.glb with two objects:
#   Crane - mast, slewing unit/cab, jib and counter-jib; origin at the mast base centre.
#   Ball  - wrecking ball, radius 1.0, origin at its centre.
# The cable hangs from the jib tip at Blender (9.0, 0, 14.6) = Godot (9.0, 14.6, 0).
import bpy, bmesh, math, os
from mathutils import Vector

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
OUT = os.path.join(ROOT, "assets", "crane")
os.makedirs(OUT, exist_ok=True)

MAST_HALF = 0.6
MAST_H = 14.0
JIB_LOW = 14.9      # bottom chords of the jib
JIB_HIGH = 15.7     # top chord of the jib
TIP = Vector((9.0, 0.0, 14.6))

mats = {}


def mat(name, color, rough, metal=0.0, coat=0.0):
    if name in mats:
        return mats[name]
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    mats[name] = m
    return m


def yellow():
    return mat("CraneYellow", (0.95, 0.55, 0.0, 1), 0.3, coat=0.6)


def steel():
    return mat("Steel", (0.18, 0.18, 0.2, 1), 0.45, metal=1.0)


def glass():
    return mat("Glass", (0.03, 0.05, 0.07, 1), 0.05)


def concrete():
    return mat("Concrete", (0.5, 0.5, 0.48, 1), 0.9)


crane_bm = bmesh.new()
mat_slots = []  # material order for the Crane mesh


def slot(m):
    if m not in mat_slots:
        mat_slots.append(m)
    return mat_slots.index(m)


def bar(p0, p1, r=0.05, sides=4, m=None):
    """A thin prism between two points (lattice member)."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = (p1 - p0)
    if axis.length < 1e-6:
        return
    d = axis.normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    u = d.cross(ref).normalized()
    v = d.cross(u).normalized()
    ring0, ring1 = [], []
    for i in range(sides):
        a = 2 * math.pi * (i + 0.5) / sides
        off = (u * math.cos(a) + v * math.sin(a)) * r
        ring0.append(crane_bm.verts.new(p0 + off))
        ring1.append(crane_bm.verts.new(p1 + off))
    mi = slot(m or yellow())
    for i in range(sides):
        j = (i + 1) % sides
        f = crane_bm.faces.new([ring0[i], ring0[j], ring1[j], ring1[i]])
        f.material_index = mi
    for ring in (ring0, ring1[::-1]):
        f = crane_bm.faces.new(ring[::-1] if ring is ring0 else ring)
        f.material_index = mi


def box(c, size, m, bevel=False):
    c = Vector(c)
    h = Vector(size) / 2
    vs = [crane_bm.verts.new(c + Vector((sx * h.x, sy * h.y, sz * h.z)))
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    mi = slot(m)
    for q in idx:
        f = crane_bm.faces.new([vs[i] for i in q])
        f.material_index = mi


def cylinder(c, r, h, m, seg=24):
    c = Vector(c)
    bot = [crane_bm.verts.new(c + Vector((math.cos(2 * math.pi * i / seg) * r, math.sin(2 * math.pi * i / seg) * r, 0))) for i in range(seg)]
    top = [crane_bm.verts.new(v.co + Vector((0, 0, h))) for v in bot]
    mi = slot(m)
    for i in range(seg):
        j = (i + 1) % seg
        crane_bm.faces.new([bot[i], bot[j], top[j], top[i]]).material_index = mi
    crane_bm.faces.new(bot[::-1]).material_index = mi
    crane_bm.faces.new(top).material_index = mi


def build_mast():
    box((0, 0, 0.3), (2.6, 2.6, 0.6), concrete())                 # footing
    box((0, 0, 0.7), (1.6, 1.6, 0.2), steel())                    # base plate
    corners = [(-MAST_HALF, -MAST_HALF), (MAST_HALF, -MAST_HALF), (MAST_HALF, MAST_HALF), (-MAST_HALF, MAST_HALF)]
    for (x, y) in corners:
        bar((x, y, 0.6), (x, y, MAST_H), r=0.1, sides=6)
    step = 1.0
    n = int((MAST_H - 0.6) / step)
    for k in range(n + 1):
        z = 0.6 + k * step
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            bar((a[0], a[1], z), (b[0], b[1], z), r=0.055)
            if k < n:
                # zig-zag diagonals, alternating direction per panel
                if k % 2 == 0:
                    bar((a[0], a[1], z), (b[0], b[1], z + step), r=0.05)
                else:
                    bar((b[0], b[1], z), (a[0], a[1], z + step), r=0.05)


def build_top():
    # Slewing ring + turntable.
    cylinder((0, 0, MAST_H), 0.95, 0.25, steel(), 32)
    box((0, 0, MAST_H + 0.45), (2.0, 1.6, 0.4), yellow())
    # Operator cab beside the jib root.
    box((0.55, 1.15, MAST_H + 0.95), (1.2, 0.9, 1.1), yellow())
    box((0.55, 1.15, MAST_H + 1.55), (1.3, 1.0, 0.1), yellow())   # roof lip
    box((1.16, 1.15, MAST_H + 1.05), (0.02, 0.75, 0.6), glass())  # front window
    box((0.55, 1.61, MAST_H + 1.05), (0.95, 0.02, 0.6), glass())  # side window
    box((0.55, 0.69, MAST_H + 1.05), (0.95, 0.02, 0.6), glass())  # inner window
    # A-frame peak (tower head).
    apex = Vector((0, 0, JIB_HIGH + 2.4))
    for (x, y) in [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]:
        bar((x, y, MAST_H + 0.65), apex, r=0.07, sides=6)
    for z in (MAST_H + 1.6, MAST_H + 2.6):
        t = (z - (MAST_H + 0.65)) / (apex.z - (MAST_H + 0.65))
        s = 0.5 * (1 - t)
        pts = [(-s, -s), (s, -s), (s, s), (-s, s)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            bar((a[0], a[1], z), (b[0], b[1], z), r=0.035)
    # Pendant ties from the peak out to the jib and counter-jib.
    bar(apex, (6.0, 0, JIB_HIGH), r=0.03, sides=4, m=steel())
    bar(apex, (-4.3, 0, JIB_LOW + 0.35), r=0.03, sides=4, m=steel())
    return apex


def build_jib():
    x0, x1 = 0.6, TIP.x + 0.3
    step = 0.75
    yl, yr = -0.45, 0.45
    n = int((x1 - x0) / step)
    def taper(x):
        return 1.0 - 0.45 * (x - x0) / (x1 - x0)
    def pts(x):
        t = taper(x)
        return (Vector((x, yl * t, JIB_LOW)), Vector((x, yr * t, JIB_LOW)), Vector((x, 0, JIB_LOW + (JIB_HIGH - JIB_LOW) * t)))
    a0, b0, c0 = pts(x0)
    a1, b1, c1 = pts(x1)
    for p, q in ((a0, a1), (b0, b1), (c0, c1)):
        bar(p, q, r=0.085, sides=6)
    for k in range(n + 1):
        x = x0 + k * step
        a, b, c = pts(x)
        bar(a, b, r=0.045)
        bar(b, c, r=0.045)
        bar(c, a, r=0.045)
        if k < n:
            a2, b2, c2 = pts(x + step)
            if k % 2 == 0:
                bar(a, c2, r=0.04)
                bar(b, c2, r=0.04)
                bar(a, b2, r=0.035)
            else:
                bar(c, a2, r=0.04)
                bar(c, b2, r=0.04)
                bar(b, a2, r=0.035)
    a, b, c = pts(x1)
    box((x1 + 0.05, 0, (JIB_LOW + c.z) / 2), (0.12, 0.6, c.z - JIB_LOW + 0.1), yellow())  # tip cap
    # Trolley and hook block at the tip; the cable hangs from TIP.
    box((TIP.x, 0, JIB_LOW - 0.08), (0.55, 0.62, 0.12), steel())
    for y in (-0.22, 0.22):
        for dx in (-0.18, 0.18):
            cylinder((TIP.x + dx, y, JIB_LOW - 0.02), 0.06, 0.06, steel(), 12)
    box((TIP.x, 0, (JIB_LOW - 0.14 + TIP.z) / 2), (0.3, 0.3, (JIB_LOW - 0.14) - TIP.z), steel())


def build_counter_jib():
    x0, x1 = -0.6, -4.6
    step = 0.8
    n = int(abs(x1 - x0) / step)
    for y in (-0.45, 0.45):
        bar((x0, y, JIB_LOW), (x1, y, JIB_LOW), r=0.06, sides=6)
        bar((x0, y, JIB_LOW + 0.35), (x1, y, JIB_LOW + 0.35), r=0.04, sides=6)
    for k in range(n + 1):
        x = x0 - k * step
        bar((x, -0.45, JIB_LOW), (x, 0.45, JIB_LOW), r=0.03)
        for y in (-0.45, 0.45):
            bar((x, y, JIB_LOW), (x, y, JIB_LOW + 0.35), r=0.03)
            if k < n:
                bar((x, y, JIB_LOW), (x - step, y, JIB_LOW + 0.35), r=0.025)
    box(((x0 + x1) / 2, 0, JIB_LOW + 0.03), (abs(x1 - x0), 0.85, 0.05), steel())  # walkway deck
    # Concrete counterweights.
    for i, x in enumerate((-3.4, -3.95)):
        box((x, 0, JIB_LOW - 0.55), (0.5, 1.0, 1.1), concrete())
    box((-2.2, 0, JIB_LOW + 0.35), (0.9, 0.8, 0.6), yellow())  # winch housing


def make_crane():
    build_mast()
    build_top()
    build_jib()
    build_counter_jib()
    bmesh.ops.remove_doubles(crane_bm, verts=crane_bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(crane_bm, faces=crane_bm.faces)
    me = bpy.data.meshes.new("Crane")
    crane_bm.to_mesh(me)
    for m in mat_slots:
        me.materials.append(m)
    ob = bpy.data.objects.new("Crane", me)
    bpy.context.collection.objects.link(ob)
    return ob


def make_ball():
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=24, radius=1.0)
    # Lifting lug: a torus-like ring on a short neck at the top.
    neck = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.28, radius2=0.18, depth=0.25)
    bmesh.ops.translate(bm, verts=neck["verts"], vec=(0, 0, 1.02))
    ring_r, tube_r = 0.22, 0.06
    seg_a, seg_b = 20, 8
    rows = []
    for i in range(seg_a):
        a = 2 * math.pi * i / seg_a
        centre = Vector((math.cos(a) * ring_r, 0, math.sin(a) * ring_r + 1.38))
        out = Vector((math.cos(a), 0, math.sin(a)))
        row = []
        for j in range(seg_b):
            b = 2 * math.pi * j / seg_b
            row.append(bm.verts.new(centre + out * math.cos(b) * tube_r + Vector((0, 1, 0)) * math.sin(b) * tube_r))
        rows.append(row)
    for i in range(seg_a):
        for j in range(seg_b):
            bm.faces.new([rows[i][j], rows[(i + 1) % seg_a][j], rows[(i + 1) % seg_a][(j + 1) % seg_b], rows[i][(j + 1) % seg_b]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Ball")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    m = mat("BallSteel", (0.09, 0.085, 0.08, 1), 0.55, metal=1.0)
    me.materials.append(m)
    ob = bpy.data.objects.new("Ball", me)
    bpy.context.collection.objects.link(ob)
    return ob


def export(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "crane.glb"), export_format="GLB", use_selection=True)
    tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs}
    print("EXPORTED crane.glb", tris, "total", sum(tris.values()))


def render(ball):
    scn = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scn.render.engine = eng
            break
        except TypeError:
            pass
    try:
        scn.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scn.render.resolution_x = scn.render.resolution_y = 640
    world = bpy.data.worlds.new("Sky")
    scn.world = world
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.55, 0.72, 0.95, 1)
    bg.inputs["Strength"].default_value = 0.8
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(mat("Grass", (0.25, 0.5, 0.18, 1), 0.9))
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.active_object
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(140))
    # Cable (render only) and ball hanging under the tip.
    drop = 3.0
    ball.location = (TIP.x, 0, TIP.z - drop - 1.45)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.03, depth=drop + 0.1,
                                        location=(TIP.x, 0, TIP.z - (drop + 0.1) / 2))
    bpy.context.active_object.data.materials.append(steel())
    bpy.ops.object.camera_add(location=(15, 15, 6))
    cam = bpy.context.active_object
    cam.rotation_euler = (Vector((2.0, 0, 9.0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 30
    scn.camera = cam
    scn.render.filepath = os.path.join(OUT, "crane.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scn.render.filepath)


bpy.ops.wm.read_factory_settings(use_empty=True)
crane = make_crane()
ball = make_ball()
export([crane, ball])
render(ball)
