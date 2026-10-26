# Builds the magnetic tile meshes and exports one .glb per shape.
# Run: blender --background --python art/src/tiles.py
# Shapes match shape_verts() in main.gd (Godot XZ plane -> Blender XY plane, y = -z).
import bpy, bmesh, math, os
from mathutils import Vector

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "tiles")
H = 0.8660254
TALL = 1.4
SHAPES = {
    "square": [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
    "triangle": [(-0.5, H / 3), (0.5, H / 3), (0, -2 * H / 3)],
    "right": [(-1 / 3, 1 / 3), (2 / 3, 1 / 3), (-1 / 3, -2 / 3)],
    "tall": [(-0.5, TALL / 3), (0.5, TALL / 3), (0, -2 * TALL / 3)],
    "big": [(-1, -1), (1, -1), (1, 1), (-1, 1)],
}
RIM_W = 0.075      # width of the solid plastic frame
RIM_T = 0.05       # frame thickness
PANEL_T = 0.018    # translucent window thickness
CORNER_R = 0.035   # rounded tile corners
RIVET_R = 0.022


def godot_to_blender(p):
    return Vector((p[0], -p[1]))


def rounded_polygon(pts, r, seg=6):
    """Polygon with each corner replaced by an arc of radius r (stays inside the original)."""
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (a - b).normalized()
        d2 = (c - b).normalized()
        half = math.acos(max(-1, min(1, d1.dot(d2)))) / 2
        dist = r / math.tan(half)
        t1 = b + d1 * dist
        t2 = b + d2 * dist
        centre = b + (d1 + d2).normalized() * (r / math.sin(half))
        a1 = math.atan2(t1.y - centre.y, t1.x - centre.x)
        a2 = math.atan2(t2.y - centre.y, t2.x - centre.x)
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        for s in range(seg + 1):
            ang = a1 + da * s / seg
            out.append(centre + Vector((math.cos(ang), math.sin(ang))) * r)
    return out


def inset_polygon(pts, d):
    """Move every edge inward by d (convex polygons)."""
    n = len(pts)
    c = sum(pts, Vector((0, 0))) / n
    lines = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        e = (b - a).normalized()
        nrm = Vector((-e.y, e.x))
        if nrm.dot(c - a) < 0:
            nrm = -nrm
        lines.append((a + nrm * d, e))
    res = []
    for i in range(n):
        (p1, e1), (p2, e2) = lines[i - 1], lines[i]
        den = e1.x * e2.y - e1.y * e2.x
        t = ((p2.x - p1.x) * e2.y - (p2.y - p1.y) * e2.x) / den
        res.append(p1 + e1 * t)
    return res


def mesh_from_outline(name, outer, inner=None, thick=0.02, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    ov = [bm.verts.new((p.x, p.y, -thick / 2)) for p in outer]
    if inner is None:
        f = bm.faces.new(ov)
        geom = [f]
    else:
        iv = [bm.verts.new((p.x, p.y, -thick / 2)) for p in inner]
        # bridge outer ring to inner ring (same vertex count)
        geom = []
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            geom.append(bm.faces.new([ov[i], ov[j], iv[j], iv[i]]))
    ext = bmesh.ops.extrude_face_region(bm, geom=geom)
    up = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=up, vec=(0, 0, thick))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if bevel > 0:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(50)
        m.harden_normals = True
    for p in me.polygons:
        p.use_smooth = True
    return ob


def material(name, color, alpha=1.0, rough=0.3, metal=0.0):
    m = bpy.data.materials.new(name)
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Alpha"].default_value = alpha
    return m


def build(shape):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    pts = [godot_to_blender(p) for p in SHAPES[shape]]
    seg = 6
    outer = rounded_polygon(pts, CORNER_R, seg)
    inner_pts = inset_polygon(pts, RIM_W)
    inner = rounded_polygon(inner_pts, CORNER_R * 0.6, seg)
    frame = mesh_from_outline("Frame", outer, inner, RIM_T, bevel=0.014)
    frame.data.materials.append(material("Frame", (0.2, 0.5, 1, 1), rough=0.28))
    # Window overlaps slightly under the frame so there is never a gap.
    win = rounded_polygon(inset_polygon(pts, RIM_W - 0.02), CORNER_R * 0.6, seg)
    panel = mesh_from_outline("Panel", win, None, PANEL_T)
    panel.data.materials.append(material("Panel", (0.2, 0.5, 1, 1), alpha=0.6, rough=0.05))
    # Silver rivets at each corner, both faces - the classic magnet-tile look.
    rivets = []
    rv_pts = inset_polygon(pts, RIM_W * 0.5)
    for p in rv_pts:
        # pull toward the corner a touch less on sharp triangle tips
        for side in (1, -1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=RIVET_R, depth=0.006,
                                                location=(p.x, p.y, side * (RIM_T / 2 + 0.002)))
            r = bpy.context.active_object
            bev = r.modifiers.new("b", "BEVEL")
            bev.width = 0.0025
            bev.segments = 2
            rivets.append(r)
    bpy.ops.object.select_all(action="DESELECT")
    for r in rivets:
        r.select_set(True)
    bpy.context.view_layer.objects.active = rivets[0]
    bpy.ops.object.join()
    rv = bpy.context.active_object
    rv.name = "Rivets"
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")  # cursor is at world origin
    bpy.ops.object.shade_smooth()
    rv.data.materials.clear()
    rv.data.materials.append(material("Rivets", (0.85, 0.86, 0.9, 1), rough=0.25, metal=1.0))
    path = os.path.abspath(os.path.join(OUT, shape + ".glb"))
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True)
    tris = sum(len(p.vertices) - 2 for o in bpy.data.objects if o.type == "MESH"
               for p in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons)
    print("EXPORTED", shape, path, "tris~", tris)


for s in SHAPES:
    build(s)
