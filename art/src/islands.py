# Builds the floating islands + props and exports them as .glb.
# Run: blender --background --python art/src/islands.py
# Blender is Z-up; the build surface of the main island is the flat disc at z = 0.
import bpy, bmesh, math, os, random
from mathutils import Vector, noise

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "islands")


def col_attr(me):
    return me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")


def make_island(name, R, depth, flat_r, seed, rings_top=14, rings_under=18, seg=96, origin=(0, 0, 0)):
    """Flat grassy top (perfectly flat inside flat_r), rounded lip, jagged rocky underside."""
    random.seed(seed)
    off = Vector((seed * 13.7, seed * 3.1, seed * 7.9))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()

    def rim_radius(a):
        p = Vector((math.cos(a), math.sin(a), 0)) * 1.6 + off
        return R * (1.0 + 0.09 * noise.noise(p) + 0.04 * noise.noise(p * 3.0))

    rows = []
    centre = bm.verts.new((0, 0, 0))
    # Top cap: concentric rings out to the lip.
    for i in range(1, rings_top + 1):
        t = i / rings_top
        row = []
        for j in range(seg):
            a = 2 * math.pi * j / seg
            rr = rim_radius(a)
            r = t * rr
            z = 0.0
            if r > flat_r:
                # gentle roll-off toward the lip
                k = (r - flat_r) / max(rr - flat_r, 0.01)
                z = -0.45 * k * k
                z += 0.05 * noise.noise(Vector((math.cos(a) * r, math.sin(a) * r, 0)) * 0.9 + off) * k
            row.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r, z)))
        rows.append(row)
    top_rows = len(rows)
    # Underside: shrinks to a craggy point.
    lip_z = -0.45
    for i in range(1, rings_under + 1):
        t = i / rings_under
        row = []
        for j in range(seg):
            a = 2 * math.pi * j / seg
            rr = rim_radius(a)
            prof = (1 - t) ** 0.65
            r = rr * prof * (1.0 + 0.04 * math.sin(t * 9.0))
            z = lip_z - depth * (t ** 1.15)
            p = Vector((math.cos(a) * r, math.sin(a) * r, z))
            n = noise.noise(p * 0.55 + off)
            n2 = noise.noise(p * 1.7 + off * 2)
            # horizontal strata + lumps
            r *= 1.0 + 0.16 * n + 0.06 * n2 + 0.05 * math.sin(z * 4.0 + n * 3)
            z += 0.25 * n2 * t
            row.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r, z)))
        rows.append(row)
    tip = bm.verts.new((0, 0, lip_z - depth * 1.12))

    top_faces, rock_faces = [], []
    for j in range(seg):
        top_faces.append(bm.faces.new([centre, rows[0][j], rows[0][(j + 1) % seg]]))
    for i in range(len(rows) - 1):
        for j in range(seg):
            jn = (j + 1) % seg
            f = bm.faces.new([rows[i][j], rows[i + 1][j], rows[i + 1][jn], rows[i][jn]])
            (top_faces if i < top_rows - 1 else rock_faces).append(f)
    for j in range(seg):
        rock_faces.append(bm.faces.new([rows[-1][j], tip, rows[-1][(j + 1) % seg]]))
    for f in top_faces:
        f.material_index = 0
    for f in rock_faces:
        f.material_index = 1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()

    # Vertex colours: grass tint variation on top, darker rock toward the bottom.
    ca = col_attr(me)
    for v in me.vertices:
        p = v.co
        if p.z > -0.5:
            n = noise.noise(p * 0.35 + off)
            c = (0.95 + 0.12 * n, 1.0 + 0.08 * n, 0.9, 1.0)
            if p.z < -0.05:  # lip: fade to earth
                k = min(1.0, -p.z / 0.45)
                c = tuple(c[i] * (1 - k) + (0.75, 0.62, 0.5, 1)[i] * k for i in range(4))
        else:
            d = min(1.0, (-p.z - 0.45) / depth)
            n = noise.noise(p * 0.8 + off)
            v_ = 1.0 - 0.55 * d + 0.08 * n
            c = (v_, v_ * 0.97, v_ * 0.95, 1.0)
        ca.data[v.index].color = c

    ob = bpy.data.objects.new(name, me)
    ob.location = origin
    bpy.context.collection.objects.link(ob)
    me.materials.append(mat("Grass", (0.35, 0.62, 0.25, 1)))
    me.materials.append(mat("Rock", (0.5, 0.45, 0.4, 1)))
    return ob


_mats = {}


def mat(name, color, rough=0.8):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    _mats[name] = m
    return m


def blob(bm, centre, radius, seed, squash=0.8, subdiv=3, strength=0.18):
    res = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    off = Vector((seed * 5.3, seed * 1.7, seed * 9.1))
    for v in res["verts"]:
        d = v.co.normalized()
        v.co = v.co * (1 + strength * noise.noise(d * 2.2 + off))
        v.co.z *= squash
        v.co += centre
    return res["verts"]


def make_tree(name, loc, seed, h=2.2):
    random.seed(seed)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    # Trunk: tapered, slightly bent cylinder.
    rings, seg = 8, 10
    prev = None
    lean = Vector((random.uniform(-0.25, 0.25), random.uniform(-0.25, 0.25), 0))
    trunk_rows = []
    for i in range(rings + 1):
        t = i / rings
        r = 0.16 * (1 - 0.55 * t) + (0.06 if i == 0 else 0)
        c = lean * (t * t) + Vector((0, 0, h * 0.62 * t))
        trunk_rows.append([bm.verts.new(c + Vector((math.cos(2 * math.pi * j / seg) * r,
                                                    math.sin(2 * math.pi * j / seg) * r, 0))) for j in range(seg)])
    trunk_faces = []
    for i in range(rings):
        for j in range(seg):
            jn = (j + 1) % seg
            trunk_faces.append(bm.faces.new([trunk_rows[i][j], trunk_rows[i][jn], trunk_rows[i + 1][jn], trunk_rows[i + 1][j]]))
    top = lean + Vector((0, 0, h * 0.62))
    n_before = len(bm.faces)
    # Canopy: a cluster of lumpy blobs.
    k = random.randint(4, 6)
    for b in range(k):
        a = 2 * math.pi * b / k + random.uniform(-0.3, 0.3)
        rr = random.uniform(0.35, 0.6)
        c = top + Vector((math.cos(a) * rr, math.sin(a) * rr, random.uniform(0.0, 0.5)))
        blob(bm, c, random.uniform(0.5, 0.75), seed * 10 + b)
    blob(bm, top + Vector((0, 0, 0.75)), 0.7, seed * 10 + 9)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.material_index = 0 if f in trunk_faces else 1
        f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ca = col_attr(me)
    for v in me.vertices:
        # canopy: darker underneath, sun-kissed on top
        if v.co.z > h * 0.45:
            g = 0.7 + 0.45 * max(0.0, min(1.0, (v.co.z - top.z + 0.3) / 1.6))
            ca.data[v.index].color = (g, g, g * 0.9, 1)
        else:
            ca.data[v.index].color = (1, 1, 1, 1)
    me.materials.append(mat("Bark", (0.42, 0.28, 0.18, 1)))
    me.materials.append(mat("Leaves", (0.3, 0.6, 0.22, 1), 0.6))
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    bpy.context.collection.objects.link(ob)
    return ob


def make_rock(name, loc, seed, size=0.5):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    blob(bm, Vector((0, 0, size * 0.25)), size, seed, squash=0.6, subdiv=2, strength=0.35)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat("Rock", (0.5, 0.45, 0.4, 1)))
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    bpy.context.collection.objects.link(ob)
    return ob


def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(path), export_format="GLB", use_selection=True,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False)
    print("EXPORTED", path)


bpy.ops.wm.read_factory_settings(use_empty=True)
main = make_island("MainIsland", R=8.0, depth=6.5, flat_r=6.6, seed=1)
export(os.path.join(OUT, "main.glb"), [main])

# Decor: satellite islands with trees + rocks, and a few props on the main island's lip.
decor = []
sats = [((-14, 6, 2.5), 2.6, 3), ((12, -9, -1.5), 2.0, 4), ((4, 15, 4.0), 1.6, 5),
        ((-9, -15, 1.0), 3.0, 6), ((17, 8, -3.5), 1.3, 7)]
for i, (pos, r, sd) in enumerate(sats):
    isl = make_island("Sat%d" % i, R=r, depth=r * 1.4, flat_r=r * 0.55, seed=sd,
                      rings_top=6, rings_under=10, seg=40, origin=pos)
    decor.append(isl)
    decor.append(make_tree("SatTree%d" % i, Vector(pos) + Vector((0.2 * r, -0.1 * r, 0)), sd, h=1.6 + r * 0.25))
    decor.append(make_rock("SatRock%d" % i, Vector(pos) + Vector((-0.45 * r, 0.3 * r, -0.02)), sd, 0.25 + 0.08 * r))
for i, a in enumerate([1.9, 2.4, 3.1, 4.0, 4.6]):
    r = 7.35
    p = Vector((math.cos(a) * r, math.sin(a) * r, -0.2))
    if i % 2 == 0:
        decor.append(make_tree("LipTree%d" % i, p, 20 + i, h=2.0 + 0.3 * (i % 3)))
    else:
        decor.append(make_rock("LipRock%d" % i, p, 30 + i, 0.55))
export(os.path.join(OUT, "decor.glb"), decor)
tri = 0
dg = bpy.context.evaluated_depsgraph_get()
for o in bpy.data.objects:
    if o.type == "MESH":
        tri += sum(len(p.vertices) - 2 for p in o.data.polygons)
print("TOTAL TRIS", tri)
