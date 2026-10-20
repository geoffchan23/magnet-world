# Groups each character's toy parts into rigid "limbs" with joint pivots and exports a .glb.
# Run: blender --background art/characters/<name>.blend --python art/src/export_characters.py
# Exported nodes: Body, Head, ArmL, ArmR, LegL, LegR, (Tail). Their origins sit at the joints,
# so the game can swing them around (see player.gd).
import bpy, os
from mathutils import Vector

HEAD = ("Head", "Eye", "Blush", "Cap", "Hair", "Ear", "Nose", "Smile", "Muzzle", "Cheek",
        "Snout", "Nostril", "Tooth", "HeadSpot", "Antenna", "Screen")


def group_of(o):
    n = o.name
    for side in ("L", "R"):
        if n.startswith((f"Arm_{side}", f"Hand_{side}", f"Sleeve_{side}", f"Paw_{side}", f"Shoulder_{side}")):
            return "Arm" + side
        if n.startswith((f"Leg_{side}", f"Shoe_{side}", f"Sole_{side}", f"Foot_{side}", f"Toe_{side}")):
            return "Leg" + side
    if n.startswith("Magnet"):
        return "ArmL"
    if n.startswith(("Tail", "TailSpike")):
        return "Tail"
    if n.startswith("Spike_"):
        return "Head" if bbox(o)[0].z > 0.7 else "Body"
    if n.startswith(HEAD):
        return "Head"
    return "Body"


def bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def centre(name):
    mn, mx = bbox(bpy.data.objects[name])
    return (mn + mx) / 2


objs = [o for o in bpy.data.objects if o.type == "MESH" and not (o.users_collection and o.users_collection[0].name == "Studio")]
groups = {}
for o in objs:
    groups.setdefault(group_of(o), []).append(o)

# Joint pivots (Blender coordinates, character faces -Y).
pivots = {}
hmn, hmx = bbox(bpy.data.objects["Head"])
pivots["Head"] = Vector((0, (hmn.y + hmx.y) / 2, hmn.z + 0.05))
pivots["Body"] = Vector((0, 0, 0))
for s in ("L", "R"):
    pivots["Arm" + s] = centre(f"Arm_{s}_cap0")
    pivots["Leg" + s] = centre(f"Leg_{s}_cap0")
if "Tail" in groups:
    mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
    for o in groups["Tail"]:
        a, b = bbox(o)
        mn = Vector(map(min, mn, a)); mx = Vector(map(max, mx, b))
    pivots["Tail"] = Vector((0, mn.y + 0.03, mn.z + 0.35 * (mx.z - mn.z)))

exported = []
for g, members in groups.items():
    bpy.ops.object.select_all(action="DESELECT")
    for o in members:
        o.select_set(True)
    bpy.context.view_layer.objects.active = members[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    if len(members) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = g
    bpy.context.scene.cursor.location = pivots[g]
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    exported.append(ob)

bpy.ops.object.select_all(action="DESELECT")
for o in exported:
    o.select_set(True)
name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "characters", name + ".glb"))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True)
print("EXPORTED", name, sorted(groups), {g: tuple(round(x, 2) for x in p) for g, p in pivots.items()})
