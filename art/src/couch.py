# "Our Living Room Couch": cream double-chaise sectional with rolled arms.
# Run: blender --background --python art/src/couch.py
# Real-world metres; Blender Z-up, the couch faces -Y. Exports assets/items/couch.glb
# plus a thumbnail render for the in-game Items menu.
import bpy, bmesh, math, os
from mathutils import Vector

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
OUT = os.path.join(ROOT, "assets", "items")
os.makedirs(OUT, exist_ok=True)

ARM_W = 0.25
CHAISE_W = 0.86
SEAT_W = 0.66
W = 2 * ARM_W + 2 * CHAISE_W + 2 * SEAT_W   # ~3.4 m
BACK_Y = 0.0          # back edge of the couch
MID_D = 1.00          # depth of the middle section
CHAISE_D = 1.65       # depth of each chaise
BASE_H = 0.30         # top of the upholstered base
SEAT_T = 0.17         # seat cushion thickness
LEG_H = 0.035

parts = []


def fabric():
    m = bpy.data.materials.get("Fabric") or bpy.data.materials.new("Fabric")
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.66, 0.61, 0.52, 1)
    b.inputs["Roughness"].default_value = 0.95
    return m


def wood():
    m = bpy.data.materials.get("Legs") or bpy.data.materials.new("Legs")
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.08, 0.06, 0.05, 1)
    b.inputs["Roughness"].default_value = 0.5
    return m


def soft_box(name, x0, x1, y0, y1, z0, z1, crown=0.0, bulge=0.0, bevel=0.03, cuts=8, tilt=0.0, pivot=None, mat=None):
    """Rounded box; crown puffs the top, bulge puffs the sides (cushion look)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    for v in bm.verts:
        u, w, h = v.co.x * 2, v.co.y * 2, v.co.z * 2      # -1..1
        p = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
        if h > 0.999:
            p.z += crown * (1 - u * u) * (1 - w * w)
        if abs(u) > 0.999:
            p.x += math.copysign(bulge, u) * (1 - w * w) * (1 - h * h)
        if abs(w) > 0.999:
            p.y += math.copysign(bulge, w) * (1 - u * u) * (1 - h * h)
        v.co = p + Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width = bevel
    bev.segments = 4
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(40)
    for poly in me.polygons:
        poly.use_smooth = True
    if tilt:
        piv = pivot or Vector(((x0 + x1) / 2, y0, z0))
        bpy.context.scene.cursor.location = piv
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        ob.rotation_euler.x = math.radians(tilt)
        ob.select_set(False)
    me.materials.append(mat or fabric())
    parts.append(ob)
    return ob


def piping(name, x0, x1, y0, y1, z, r=0.009, inset=0.012, tilt=0.0, pivot=None):
    """Welt cord around a cushion's top edge."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    pts = [(x0 + inset, y0 + inset), (x1 - inset, y0 + inset), (x1 - inset, y1 - inset), (x0 + inset, y1 - inset)]
    sp.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        sp.points[i].co = (x, y, z, 1)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    if tilt:
        bpy.context.scene.cursor.location = pivot
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        ob.rotation_euler.x = math.radians(tilt)
        ob.select_set(False)
    cu.materials.append(fabric())
    parts.append(ob)
    return ob


def rolled_arm(name, xc, y0, y1, outward):
    """Upholstered arm with a rolled top that flares outward."""
    x0, x1 = xc - ARM_W / 2, xc + ARM_W / 2
    soft_box(name + "_Body", x0, x1, y0, y1, LEG_H, 0.55, bevel=0.04, cuts=4)
    # roll along the depth of the arm
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.135, depth=(y1 - y0) - 0.02,
                                        location=(xc + outward * 0.045, (y0 + y1) / 2, 0.545),
                                        rotation=(math.radians(90), 0, 0))
    roll = bpy.context.active_object
    roll.name = name + "_Roll"
    bev = roll.modifiers.new("bevel", "BEVEL")
    bev.width = 0.03
    bev.segments = 4
    bpy.ops.object.shade_smooth()
    roll.data.materials.append(fabric())
    parts.append(roll)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    x = -W / 2
    xl_arm = x + ARM_W / 2
    x += ARM_W
    xl_chaise = (x, x + CHAISE_W)
    x += CHAISE_W
    x_seats = [(x, x + SEAT_W), (x + SEAT_W, x + 2 * SEAT_W)]
    x += 2 * SEAT_W
    xr_chaise = (x, x + CHAISE_W)
    x += CHAISE_W
    xr_arm = x + ARM_W / 2
    front_mid = BACK_Y - MID_D
    front_ch = BACK_Y - CHAISE_D

    # Upholstered base / frame.
    for (a, b) in (xl_chaise, xr_chaise):
        soft_box("Base_Chaise", a, b, front_ch, BACK_Y, LEG_H, BASE_H, bevel=0.025, cuts=3)
    soft_box("Base_Mid", x_seats[0][0], x_seats[1][1], front_mid, BACK_Y, LEG_H, BASE_H, bevel=0.025, cuts=3)
    # Back frame behind the back cushions.
    soft_box("Back_Frame", -W / 2 + ARM_W - 0.02, W / 2 - ARM_W + 0.02, BACK_Y - 0.2, BACK_Y, LEG_H, 0.66,
             crown=0.02, bevel=0.05, cuts=4)
    rolled_arm("Arm_L", xl_arm, front_ch, BACK_Y, -1)
    rolled_arm("Arm_R", xr_arm, front_ch, BACK_Y, 1)

    # Seat cushions: two in the middle, a long one on each chaise.
    seat_top = BASE_H + SEAT_T
    for i, (a, b) in enumerate(x_seats):
        soft_box("Seat_%d" % i, a + 0.005, b - 0.005, front_mid + 0.01, BACK_Y - 0.21, BASE_H, seat_top,
                 crown=0.035, bulge=0.012, bevel=0.035)
        piping("SeatPipe_%d" % i, a + 0.005, b - 0.005, front_mid + 0.01, BACK_Y - 0.21, seat_top - 0.006)
    for side, (a, b) in (("L", xl_chaise), ("R", xr_chaise)):
        soft_box("Chaise_" + side, a + 0.005, b - 0.005, front_ch + 0.01, BACK_Y - 0.21, BASE_H, seat_top,
                 crown=0.03, bulge=0.012, bevel=0.035)
        piping("ChaisePipe_" + side, a + 0.005, b - 0.005, front_ch + 0.01, BACK_Y - 0.21, seat_top - 0.006)

    # Back cushions, leaning back a little: chaise, seat, seat, chaise.
    backs = [xl_chaise, x_seats[0], x_seats[1], xr_chaise]
    for i, (a, b) in enumerate(backs):
        y0, y1 = BACK_Y - 0.43, BACK_Y - 0.2
        z0, z1 = seat_top - 0.02, seat_top + 0.47
        piv = Vector(((a + b) / 2, y1, z0))
        soft_box("Back_%d" % i, a + 0.01, b - 0.01, y0, y1, z0, z1, crown=0.0, bulge=0.035,
                 bevel=0.045, tilt=-13, pivot=piv)

    # Short dark legs, barely visible under the base.
    for (px, py) in [(-W / 2 + 0.08, BACK_Y - 0.08), (W / 2 - 0.08, BACK_Y - 0.08),
                     (-W / 2 + 0.08, front_ch + 0.08), (W / 2 - 0.08, front_ch + 0.08),
                     (0, BACK_Y - 0.08), (0, front_mid + 0.08)]:
        soft_box("Leg", px - 0.035, px + 0.035, py - 0.035, py + 0.035, 0, LEG_H + 0.01, bevel=0.008, cuts=1, mat=wood())

    # Bake curves + modifiers into meshes.
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.convert(target="MESH")


def export():
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "couch.glb"), export_format="GLB",
                              use_selection=True, export_apply=True)
    dg = bpy.context.evaluated_depsgraph_get()
    tris = sum(sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons)
               for o in bpy.data.objects if o.type == "MESH")
    print("EXPORTED couch.glb, objects:", len([o for o in bpy.data.objects if o.type == "MESH"]), "tris:", tris)


def thumbnail():
    """Soft studio render used as the Items-menu card."""
    scn = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scn.render.engine = eng
            break
        except TypeError:
            pass
    scn.render.resolution_x = scn.render.resolution_y = 640
    scn.render.film_transparent = False
    world = bpy.data.worlds.new("W")
    scn.world = world
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.82, 0.86, 0.92, 1)
    bg.inputs["Strength"].default_value = 0.6
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    floor = bpy.context.active_object
    fm = bpy.data.materials.new("Floor")
    next(n for n in fm.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (0.75, 0.78, 0.84, 1)
    floor.data.materials.append(fm)
    # Woven fabric look for the render (box-projected Poly Haven cotton weave).
    tex = os.path.join(ROOT, "assets", "textures")
    m = fabric()
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (5, 5, 5)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    def img(name, non_color=False):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(tex, name))
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        n.projection = "BOX"
        n.projection_blend = 0.3
        nt.links.new(mapping.outputs["Vector"], n.inputs["Vector"])
        return n
    alb = img("fabric_albedo.jpg")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.35
    mix.inputs["A"].default_value = (0.66, 0.61, 0.52, 1)
    nt.links.new(alb.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    nrm = img("fabric_normal.jpg", True)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = 0.8
    nt.links.new(nrm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    try:
        scn.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    for loc, energy, size in [((-3, -4, 4), 450, 4), ((4, -2, 3), 180, 3), ((0, 3, 4), 150, 3)]:
        bpy.ops.object.light_add(type="AREA", location=loc)
        lt = bpy.context.active_object
        lt.data.energy = energy
        lt.data.size = size
        lt.rotation_euler = (Vector((0, -0.6, 0.4)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.object.camera_add(location=(2.6, -4.6, 2.6))
    cam = bpy.context.active_object
    cam.rotation_euler = (Vector((0, -0.65, 0.35)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 40
    scn.camera = cam
    scn.render.filepath = os.path.join(OUT, "couch.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scn.render.filepath)


build()
export()
thumbnail()
