# Shared helpers for the NPC figures (art/src/npcs.py): lean low-poly wrappers around toykit,
# limb tagging, and a joint-pivot exporter that writes clean glb nodes (identity rotation/scale,
# origin at the joint) so player.gd-style animation (rotate a limb about its origin) just works.
import sys, os, math
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "art", "characters"))
import bpy, bmesh
import toykit
from toykit import mat, srgb, surf, facing, arc_on, finalize, studio
from mathutils import Vector, Quaternion, Euler

# ------------------------------------------------------------------ limb tagging
CUR = ["Body"]


class limb:
    """`with limb("ArmL"): ...` tags every part made inside the block with that limb."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.prev = CUR[0]
        CUR[0] = self.name

    def __exit__(self, *a):
        CUR[0] = self.prev


if not hasattr(toykit, "_untagged_obj"):
    toykit._untagged_obj = toykit._obj
_orig_obj = toykit._untagged_obj


def _tagged_obj(name, me, m, loc=(0, 0, 0), smooth=True, parent=None):
    o = _orig_obj(name, me, m, loc, smooth, parent)
    o["limb"] = CUR[0]
    return o


toykit._obj = _tagged_obj


def reset(name):
    CUR[0] = "Body"
    return toykit.reset(name)


# ------------------------------------------------------------------ lean primitives
# DETAIL scales every segment count; build() lowers it until the figure fits its triangle budget,
# so parts keep clean, regular topology (no decimation facets). hero=True parts (heads, bodies)
# are protected: they only lose detail at the square root of the rate.
DETAIL = [1.0]


def _d(n, lo, hero=False, even=True):
    f = DETAIL[0] ** (0.5 if hero else 1.0)
    if hero:
        lo = max(lo, int(n * 0.8))
    v = max(min(lo, n), int(round(n * f)))
    return v + (v % 2) if even else v


def auto_seg(size):
    """UV-sphere resolution by size, so tiny bits don't eat the triangle budget."""
    for lim, sr in ((0.15, (24, 12)), (0.09, (16, 8)), (0.05, (12, 6)), (0.03, (10, 5)), (0.018, (8, 4)), (0.0, (6, 3))):
        if size >= lim:
            return sr


def _size(scale):
    x, y, z = sorted(scale)
    return (x * y * z) ** (1 / 3) * 0.5 + (y * z) ** 0.5 * 0.5


FLOOR = {24: 16, 20: 14, 18: 12, 16: 12, 14: 10, 12: 10, 10: 8, 8: 8, 6: 6}


def _sr(scale, seg, ring, hero):
    a, b = auto_seg(_size(scale))
    seg = seg or a
    ring = ring or (seg // 2 if seg != a else b)
    lo = FLOOR.get(seg, max(6, int(seg * 0.7)))
    return _d(seg, lo, hero), _d(ring, max(3, lo // 2), hero, even=False)


def blob(name, center, radii, m, bumps=(), seg=28, ring=14, rot=None, hero=True, squash_below=None):
    """One smooth ellipsoid with soft bumps pushed out of it: (direction, height, width_radians[, sweep]).
    Hair tufts, fur ruffs, goo drips: a single clean mesh instead of dozens of parts."""
    seg, ring = _d(seg, FLOOR.get(seg, 12), hero), _d(ring, 7, hero, even=False)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    bs = [(Vector(b[0]).normalized(), b[1], b[2], Vector(b[3]) if len(b) > 3 else Vector()) for b in bumps]
    for v in bm.verts:
        d = v.co.normalized()
        off = 0.0
        sweep = Vector()
        for bd, h, w, sw in bs:
            ang = d.angle(bd, 0.0)
            k = math.exp(-(ang / w) ** 2)
            off += h * k
            sweep += sw * k
        if squash_below is not None and d.z < squash_below:
            d = Vector((d.x, d.y, squash_below + (d.z - squash_below) * 0.35))
        v.co = Vector((d.x * radii[0], d.y * radii[1], d.z * radii[2])) * 1.0 + d * off + sweep
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m, center)
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    return o


def sph(name, loc, scale, m, seg=None, ring=None, rot=None, hero=False):
    if isinstance(scale, (int, float)):
        scale = (scale, scale, scale)
    seg, ring = _sr(scale, seg, ring, hero)
    return toykit.sphere(name, loc, scale, m, seg=seg, ring=ring, rot=rot)


def hsph(name, loc, scale, m, keep_above=0.0, seg=None, ring=None, rot=None, hero=False):
    seg, ring = _sr(scale, seg, ring, hero)
    return toykit.half_sphere(name, loc, scale, m, keep_above=keep_above, seg=seg, ring=ring, rot=rot)


def box(name, loc, size, m, bevel=0.02, rot=None, segs=None):
    """Rounded box; 1 bevel segment for small boxes (smooth-shaded it still reads soft)."""
    segs = segs or (2 if min(size) >= 0.06 and DETAIL[0] > 0.6 else 1)
    bevel = min(bevel, min(size) * 0.45)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=segs, profile=0.5, affect="EDGES")
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m, loc)
    if rot is not None:
        if isinstance(rot, Quaternion):
            o.rotation_mode = "QUATERNION"
            o.rotation_quaternion = rot
        else:
            o.rotation_euler = rot
    return o


def _cyl_mesh(name, r, h, r2=None, seg=12, bevel=0.0):
    """Lean capped cylinder/frustum along Z: one bevel ring per cap (soft edge), fan-free ngon caps."""
    r2 = r if r2 is None else r2
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    zs = []
    if bevel > 0:
        b = min(bevel, h * 0.3, min(r, r2) * 0.4)
        prof = [(r - b, -h / 2), (r, -h / 2 + b), (r2, h / 2 - b), (r2 - b, h / 2)]
    else:
        prof = [(r, -h / 2), (r2, h / 2)]
    for rr, z in prof:
        rings.append([bm.verts.new((rr * math.cos(2 * math.pi * i / seg), rr * math.sin(2 * math.pi * i / seg), z))
                      for i in range(seg)])
    for k in range(len(rings) - 1):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bm.to_mesh(me)
    bm.free()
    # flat caps: mark the cap rims sharp so smooth shading doesn't smear across them
    for e in me.edges:
        v0, v1 = me.vertices[e.vertices[0]].co, me.vertices[e.vertices[1]].co
        if abs(v0.z - v1.z) < 1e-6 and abs(abs(v0.z) - h / 2) < 1e-6:
            e.use_edge_sharp = True
    return me


def cyl(name, loc, r, h, m, r2=None, seg=None, rot=None, bevel=None):
    rr = max(r, r2 or 0)
    seg = seg or (20 if rr >= 0.08 else 16 if rr >= 0.045 else 12 if rr >= 0.02 else 8)
    seg = _d(seg, max(8, int(seg * 0.75)))
    if bevel is None:
        bevel = min(rr * 0.18, 0.012)
    if isinstance(rot, tuple) and len(rot) == 3:
        rot = Euler(rot).to_quaternion()
    o = toykit._obj(name, _cyl_mesh(name, r, h, r2, seg, bevel), m, loc)
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    return o


def cyl_between(name, a, b, r, m, r2=None, seg=None, bevel=None):
    a, b = Vector(a), Vector(b)
    d = b - a
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return cyl(name, (a + b) / 2, r, d.length, m, r2=r2, seg=seg, rot=q, bevel=bevel)


def cone(name, base, direction, r, h, m, seg=10, subsurf=0, flatten=1.0, twist=0.0):
    return toykit.cone(name, base, direction, r, h, m, seg=_d(seg, 6), subsurf=subsurf, flatten=flatten, twist=twist)


def tube(name, pts, m, r=0.03, radii=None, caps=True, res=2, br=1, cap_seg=None):
    """Smooth tube (8 sides at br=1, 12 at br=2) through points; small sphere caps."""
    o = toykit.tube(name, pts, m, radius=r, radii=radii, caps=False, res=max(2, round(res * DETAIL[0] ** 0.5)),
                    bevel_res=br)
    if caps:
        for i in (0, len(pts) - 1):
            rr = r * (radii[i] if radii else 1.0)
            sph(f"{name}_cap{i}", pts[i], (rr, rr, rr), m, seg=cap_seg)
    return o


def torus(name, loc, major, minor, m, rot=(0, 0, 0), scale=(1, 1, 1), seg=None, mseg=None):
    seg = _d(seg or (20 if major >= 0.15 else 16 if major >= 0.06 else 12 if major >= 0.03 else 8), 8)
    mseg = _d(mseg or (6 if minor >= 0.025 else 5 if minor >= 0.012 else 4), 4, even=False)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ring_ = []
        for j in range(mseg):
            b = 2 * math.pi * j / mseg
            rr = major + minor * math.cos(b)
            ring_.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), minor * math.sin(b))))
        rings.append(ring_)
    for i in range(seg):
        for j in range(mseg):
            a, b = rings[i][j], rings[i][(j + 1) % mseg]
            c, d = rings[(i + 1) % seg][(j + 1) % mseg], rings[(i + 1) % seg][j]
            bm.faces.new((a, b, c, d))
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m, loc)
    if isinstance(rot, Quaternion):
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    else:
        o.rotation_euler = rot
    o.scale = scale
    return o


def aim(d, twist=0.0):
    """Quaternion taking local +Z onto direction d (then twisted about it)."""
    return Vector((0, 0, 1)).rotation_difference(Vector(d).normalized()) @ Quaternion((0, 0, 1), twist)


def eye(name, center, radii, direction, w, h, black, white, depth=0.02, seg=12, shine2=True):
    p, n = surf(center, radii, direction)
    q = facing(n)
    sph(name, p - n * depth * 0.35, (w, depth, h), black, seg=seg, ring=seg // 2, rot=q)
    side = q @ Vector((1, 0, 0))
    up = q @ Vector((0, 0, 1))
    sgn = 1 if direction[0] >= 0 else -1
    hl = p + n * depth * 0.55 + up * h * 0.38 - side * w * 0.3 * sgn
    s = min(w, h) * 0.34
    sph(name + "_Shine", hl, (s, s * 0.6, s), white, seg=8, ring=4, rot=q)
    if not shine2:
        return
    hl2 = p + n * depth * 0.5 - up * h * 0.35 + side * w * 0.3 * sgn
    s2 = s * 0.45
    sph(name + "_Shine2", hl2, (s2, s2 * 0.6, s2), white, seg=6, ring=4, rot=q)


def decal(name, center, radii, direction, scale, m, sink=0.4, seg=10, ring=4):
    p, n = surf(center, radii, direction)
    return sph(name, p - n * scale[1] * sink, scale, m, seg=seg, ring=ring, rot=facing(n))


def on(center, radii, direction, out=0.0):
    p, n = surf(center, radii, direction)
    return p + n * out, n


def common_mats():
    return (mat("EyeBlack", "141821", rough=0.08, coat=1.0),
            mat("EyeShine", "ffffff", rough=0.2, coat=0.0, emit="ffffff", emit_strength=1.5))


# ------------------------------------------------------------------ export
def mesh_objs():
    return [o for o in bpy.data.objects if o.type == "MESH" and "limb" in o.keys()]


def tri_report():
    per = {}
    for o in mesh_objs():
        o.data.calc_loop_triangles()
        per[o["limb"]] = per.get(o["limb"], 0) + len(o.data.loop_triangles)
    return per


def bake_transforms():
    bpy.ops.object.select_all(action="DESELECT")
    for o in mesh_objs():
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def height():
    zs = [(o.matrix_world @ v.co).z for o in mesh_objs() for v in o.data.vertices]
    return min(zs), max(zs)


def extents():
    pts = [o.matrix_world @ v.co for o in mesh_objs() for v in o.data.vertices]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def export(name, pivots):
    """Join each limb's parts into one node with its origin at pivots[limb]; write the glb."""
    groups = {}
    for o in mesh_objs():
        groups.setdefault(o["limb"], []).append(o)
    missing = set(groups) - set(pivots)
    assert not missing, f"no pivot for {missing}"
    exported = []
    for g, members in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for o in members:
            o.select_set(True)
        bpy.context.view_layer.objects.active = members[0]
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        # Location into the mesh too, so the node ends up with pure translation = pivot.
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        if len(members) > 1:
            bpy.ops.object.join()
        ob = bpy.context.view_layer.objects.active
        ob.name = g
        ob.data.name = g
        bpy.context.scene.cursor.location = Vector(pivots[g])
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        exported.append(ob)
    bpy.ops.object.select_all(action="DESELECT")
    for o in exported:
        o.select_set(True)
    out = os.path.join(ROOT, "assets", "characters", f"npc_{name}.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True)
    print("EXPORTED", out)
    for g in sorted(pivots):
        if g in groups:
            p = Vector(pivots[g])
            # Godot coords: (x, z, -y)
            print(f"  NODE {g:9s} blender=({p.x:+.3f},{p.y:+.3f},{p.z:+.3f})  godot=({p.x:+.3f},{p.z:+.3f},{-p.y:+.3f})")
    return out


# ------------------------------------------------------------------ rendering
def cam_at(target, dist, yaw, pitch, lens=60):
    cam = bpy.context.scene.camera
    cam.data.lens = lens
    tgt = Vector(target)
    y, p = math.radians(yaw), math.radians(pitch)
    off = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p))) * dist
    cam.location = tgt + off
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-off).to_track_quat("-Z", "Y")


def render(path, res=1024, samples=None):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = res
    if samples:
        sc.eevee.taa_render_samples = samples
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def downscale(src, dst, size=320):
    img = bpy.data.images.load(src)
    img.scale(size, size)
    img.filepath_raw = dst
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def contact_sheet(paths, dst, cols=3, cell=420):
    """Tile renders into one image (pure bpy, no PIL)."""
    imgs = [bpy.data.images.load(p) for p in paths]
    rows = (len(imgs) + cols - 1) // cols
    W, H = cols * cell, rows * cell
    out = [1.0] * (W * H * 4)
    for k, im in enumerate(imgs):
        im.scale(cell, cell)
        px = list(im.pixels)
        cx, cy = (k % cols) * cell, (rows - 1 - k // cols) * cell
        for y in range(cell):
            row = px[y * cell * 4:(y + 1) * cell * 4]
            o = ((cy + y) * W + cx) * 4
            out[o:o + cell * 4] = row
    sheet = bpy.data.images.new("sheet", W, H, alpha=True)
    sheet.pixels = out
    sheet.filepath_raw = dst
    sheet.file_format = "PNG"
    sheet.save()


def fit_budget(budget=4800, floor=40, min_ratio=0.22):
    """Collapse-decimate parts (flattest areas go first) until the figure fits the triangle budget.
    Parts under `floor` tris are left alone; bigger parts share the cut in proportion."""
    def tri(o):
        o.data.calc_loop_triangles()
        return len(o.data.loop_triangles)

    for _ in range(4):
        objs = mesh_objs()
        counts = {o.name: tri(o) for o in objs}
        total = sum(counts.values())
        if total <= budget:
            return total
        big = [o for o in objs if counts[o.name] > floor]
        small = total - sum(counts[o.name] for o in big)
        ratio = max(min_ratio, (budget - small) / max(1, total - small))
        for o in big:
            n = counts[o.name]
            r = max(ratio, floor / n)
            if r >= 0.98:
                continue
            mod = o.modifiers.new("Dec", "DECIMATE")
            mod.decimate_type = "COLLAPSE"
            mod.ratio = r
            dg = bpy.context.evaluated_depsgraph_get()
            me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
            old = o.data
            o.modifiers.clear()
            o.data = me
            me.name = o.name
            if old.users == 0:
                bpy.data.meshes.remove(old)
    return sum(tri(o) for o in mesh_objs())
