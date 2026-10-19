"""Helpers for building toy-style characters from primitives in Blender (background mode)."""
import bpy, bmesh, math
from mathutils import Vector, Quaternion

STATE = {"root": None, "coll": None}
MATS = {}


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def reset(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    STATE["coll"] = coll
    root = bpy.data.objects.new(f"{name}_Root", None)
    root.empty_display_type = "PLAIN_AXES"
    coll.objects.link(root)
    STATE["root"] = root
    return root


def mat(name, color, rough=0.32, coat=0.5, metal=0.0, emit=None, emit_strength=3.0, sss=0.0):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*srgb(color), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.12
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (0.08, 0.04, 0.03)
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(emit), 1)
        b.inputs["Emission Strength"].default_value = emit_strength
    m.diffuse_color = (*srgb(color), 1)
    MATS[name] = m
    return m


def _obj(name, me, m, loc=(0, 0, 0), smooth=True, parent=None):
    if m is not None:
        me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    STATE["coll"].objects.link(o)
    o.location = loc
    o.parent = parent or STATE["root"]
    return o


def sphere(name, loc, scale, m, seg=24, ring=12, rot=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    o = _obj(name, me, m, loc)
    o.scale = scale
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    return o


def half_sphere(name, loc, scale, m, keep_above=0.0, seg=24, ring=12, rot=None):
    """Sphere cut by local plane z=keep_above, keeping the top part."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, keep_above), plane_no=(0, 0, 1), clear_inner=True)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges)
    bm.to_mesh(me)
    bm.free()
    o = _obj(name, me, m, loc)
    o.scale = scale
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    return o


def rbox(name, loc, size, m, bevel=0.03, rot=None, subsurf=1):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=2, profile=0.5, affect="EDGES")
    bm.to_mesh(me)
    bm.free()
    o = _obj(name, me, m, loc)
    if subsurf:
        mod = o.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = mod.render_levels = subsurf
    if rot is not None:
        o.rotation_euler = rot
    return o


def cyl(name, loc, r, h, m, r2=None, seg=24, rot=None, bevel=0.01, subsurf=1):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    if bevel:
        caps = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6]
        bmesh.ops.bevel(bm, geom=caps, offset=bevel, segments=2, profile=0.5, affect="EDGES")
    # inset caps so subsurf keeps them flat
    caps = [f for f in bm.faces if len(f.verts) > 4]
    if caps:
        bmesh.ops.inset_region(bm, faces=caps, thickness=min(r, r2 or r) * 0.25)
    bm.to_mesh(me)
    bm.free()
    o = _obj(name, me, m, loc)
    if subsurf:
        mod = o.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = mod.render_levels = subsurf
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    return o


def cone(name, base, direction, r, h, m, seg=16, subsurf=1, flatten=1.0, twist=0.0):
    """Rounded cone whose base sits at `base` and points along `direction`."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=seg, radius1=r, radius2=r * 0.15, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    bmesh.ops.scale(bm, vec=(1, flatten, 1), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    o = _obj(name, me, m, base)
    if subsurf:
        mod = o.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = mod.render_levels = subsurf
    o.rotation_mode = "QUATERNION"
    q = Vector((0, 0, 1)).rotation_difference(Vector(direction).normalized())
    o.rotation_quaternion = q @ Quaternion((0, 0, 1), twist)
    return o


def tube(name, pts, m, radius=0.03, radii=None, caps=True, res=8, bevel_res=3):
    """Smooth tube through points with optional per-point radius multipliers; rounded ends."""
    cu = bpy.data.curves.new(name + "_curve", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = bevel_res
    cu.resolution_u = res
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
        bp.radius = radii[i] if radii else 1.0
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    STATE["coll"].objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    me.name = name
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    o = _obj(name, me, None)
    me.materials.clear()
    me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    if caps:
        for i in (0, len(pts) - 1):
            rr = radius * (radii[i] if radii else 1.0)
            sphere(f"{name}_cap{i}", pts[i], (rr, rr, rr), m, seg=12, ring=6)
    return o


def torus(name, loc, major, minor, m, rot=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=32,
                                     minor_segments=10, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    for c in o.users_collection:
        c.objects.unlink(o)
    STATE["coll"].objects.link(o)
    o.data.materials.append(m)
    for p in o.data.polygons:
        p.use_smooth = True
    o.scale = scale
    o.parent = STATE["root"]
    return o


def surf(center, radii, direction):
    """Point + outward normal on an axis-aligned ellipsoid, along a direction from its center."""
    c = Vector(center)
    r = Vector(radii)
    d = Vector(direction).normalized()
    t = 1.0 / math.sqrt((d.x / r.x) ** 2 + (d.y / r.y) ** 2 + (d.z / r.z) ** 2)
    p = c + d * t
    n = Vector(((p.x - c.x) / r.x ** 2, (p.y - c.y) / r.y ** 2, (p.z - c.z) / r.z ** 2)).normalized()
    return p, n


def facing(n):
    """Rotation taking local -Y (the 'front' of decals/eyes) onto normal n."""
    return Vector((0, -1, 0)).rotation_difference(Vector(n))


def decal(name, center, radii, direction, scale, m, sink=0.4, seg=16, ring=8):
    p, n = surf(center, radii, direction)
    return sphere(name, p - n * scale[1] * sink, scale, m, seg=seg, ring=ring, rot=facing(n))


def eye(name, center, radii, direction, w, h, black, white, depth=0.022):
    p, n = surf(center, radii, direction)
    q = facing(n)
    sphere(name, p - n * depth * 0.35, (w, depth, h), black, seg=20, ring=10, rot=q)
    side = q @ Vector((1, 0, 0))
    up = q @ Vector((0, 0, 1))
    hl = p + n * depth * 0.55 + up * h * 0.38 - side * w * 0.3 * (1 if direction[0] >= 0 else -1)
    s = min(w, h) * 0.34
    sphere(name + "_Shine", hl, (s, s * 0.6, s), white, seg=12, ring=6, rot=q)
    hl2 = p + n * depth * 0.5 - up * h * 0.35 + side * w * 0.3 * (1 if direction[0] >= 0 else -1)
    s2 = s * 0.45
    sphere(name + "_Shine2", hl2, (s2, s2 * 0.6, s2), white, seg=10, ring=5, rot=q)


def arc_on(center, radii, dirs, lift=0.004):
    out = []
    for d in dirs:
        p, n = surf(center, radii, d)
        out.append(p + n * lift)
    return out


# ------------------------------------------------------------------ finalize / studio / render

def finalize():
    """Apply modifiers so the .blend is game-ready; return triangle count."""
    dg = bpy.context.evaluated_depsgraph_get()
    tris = 0
    for o in list(STATE["coll"].objects):
        if o.type != "MESH":
            continue
        if o.modifiers:
            me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
            old = o.data
            o.modifiers.clear()
            o.data = me
            me.name = o.name
            if old.users == 0:
                bpy.data.meshes.remove(old)
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    return tris


def studio(backdrop="dde9ff", target=(0, 0, 0.5), dist=2.15, yaw=32, pitch=14, lens=60):
    sc = bpy.context.scene
    st = bpy.data.collections.new("Studio")
    sc.collection.children.link(st)

    world = bpy.data.worlds.new("World")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*srgb(backdrop), 1)
    bg.inputs["Strength"].default_value = 0.45

    # Cyclorama backdrop
    me = bpy.data.meshes.new("Backdrop")
    bm = bmesh.new()
    W, F, B, Hh = 8.0, -8.0, 2.2, 8.0
    v = [bm.verts.new(p) for p in [(-W, F, 0), (W, F, 0), (W, B, 0), (-W, B, 0), (W, B, Hh), (-W, B, Hh)]]
    bm.faces.new((v[0], v[1], v[2], v[3]))
    bm.faces.new((v[3], v[2], v[4], v[5]))
    bm.edges.ensure_lookup_table()
    joint = [e for e in bm.edges if set(e.verts) == {v[2], v[3]}]
    bmesh.ops.bevel(bm, geom=joint, offset=1.6, segments=16, profile=0.5, affect="EDGES")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    bd = bpy.data.objects.new("Backdrop", me)
    st.objects.link(bd)
    bmat = bpy.data.materials.new("Backdrop")
    try:
        bmat.use_nodes = True
    except Exception:
        pass
    b = next(n for n in bmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*srgb(backdrop), 1)
    b.inputs["Roughness"].default_value = 0.85
    me.materials.append(bmat)

    tgt = Vector(target)

    def light(name, pos, energy, size, color="ffffff"):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = srgb(color)
        lo = bpy.data.objects.new(name, ld)
        st.objects.link(lo)
        lo.location = pos
        lo.rotation_mode = "QUATERNION"
        lo.rotation_quaternion = (tgt - Vector(pos)).to_track_quat("-Z", "Y")
        return lo

    light("Key", (-2.0, -2.6, 3.0), 420, 2.5, "fff3e6")
    light("Fill", (2.8, -1.6, 1.4), 160, 3.0, "e6f0ff")
    light("Rim", (1.2, 2.4, 2.6), 260, 1.6)
    light("Top", (0, 0, 4.0), 120, 4.0)

    cd = bpy.data.cameras.new("Camera")
    cd.lens = lens
    cam = bpy.data.objects.new("Camera", cd)
    st.objects.link(cam)
    y, p = math.radians(yaw), math.radians(pitch)
    off = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p))) * dist
    cam.location = tgt + off
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-off).to_track_quat("-Z", "Y")
    sc.camera = cam

    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = 1024
    sc.render.film_transparent = False
    ee = sc.eevee
    for attr, val in (("taa_render_samples", 96), ("use_raytracing", True), ("use_shadows", True),
                      ("shadow_ray_count", 2), ("shadow_step_count", 8), ("use_gtao", True)):
        try:
            setattr(ee, attr, val)
        except Exception:
            pass
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Punchy"
    except Exception:
        pass


def render_and_save(png, blend):
    sc = bpy.context.scene
    sc.render.filepath = png
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
