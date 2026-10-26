# The Giant who comes to smash your build: a toy-vinyl likeness of Levi.
# Run: blender --background --python art/src/giant.py
# Then: blender --background art/characters/giant.blend --python art/src/export_characters.py
# Faces -Y, feet on z=0, ~2.0 units tall. Part names follow export_characters.py:
# Arm_*_cap0 sits at the shoulder and Leg_*_cap0 at the hip (those become the joint pivots).
# Naming follows the explorers (L = -X). Facing -Y, Levi's own left hand is on +X, so the
# watch sits on the "R"-named arm.
import sys, os, math
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "art", "characters"))
import toykit
from toykit import *
from mathutils import Vector, Quaternion
import bpy

FRONT_Y = -0.112  # front face of the t-shirt (print decals sit here)


def flat(name, loc, scale, m, rot_y=0.0):
    """Thin flat inset shape on the shirt front."""
    return sphere(name, loc, scale, m, seg=20, ring=8, rot=Quaternion((0, 1, 0), rot_y))


def levi():
    reset("Giant")
    skin = mat("Skin", "c98f62", rough=0.45, coat=0.25, sss=0.12)
    hair = mat("Hair", "221913", rough=0.55, coat=0.15)  # near-black with a dark-brown sheen
    iris = mat("EyeBrown", "3a2214", rough=0.06, coat=1.0)
    shine = mat("EyeShine", "ffffff", rough=0.2, coat=0.0, emit="ffffff", emit_strength=1.5)
    shirt = mat("Shirt", "1b1b20", rough=0.62, coat=0.1)
    shorts = mat("Shorts", "1f4fd8", rough=0.4, coat=0.3)
    mouth = mat("Mouth", "3a0f12", rough=0.5, coat=0.1)
    tooth = mat("Tooth", "fffdf6", rough=0.25, coat=0.7)
    lip = mat("Lip", "d98a7c", rough=0.45, coat=0.2)
    blush = mat("Blush", "e8846f", rough=0.6, coat=0.0)
    yellow = mat("PrintYellow", "ffd23a", rough=0.45, coat=0.2, emit="ffd23a", emit_strength=0.25)
    cream = mat("PrintCream", "fff3d6", rough=0.45, coat=0.2, emit="fff3d6", emit_strength=0.2)
    teal = mat("PrintTeal", "45d0c8", rough=0.45, coat=0.2, emit="45d0c8", emit_strength=0.2)
    orange = mat("PrintOrange", "ff8a1f", rough=0.45, coat=0.2, emit="ff8a1f", emit_strength=0.2)
    watch = mat("Watch", "1d2540", rough=0.3, coat=0.6)

    # ---- head
    hc, hr = (0, -0.01, 1.66), (0.21, 0.2, 0.235)
    sphere("Head", hc, hr, skin, seg=30, ring=15)
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        sphere(f"Ear_{side}", (s * 0.207, 0.015, 1.64), (0.03, 0.045, 0.06), skin, seg=14, ring=7)
        eye(f"Eye_{side}", hc, hr, (s * 0.36, -1, 0.01), 0.044, 0.05, iris, shine, depth=0.02)
        # soft, slightly thick brows
        tube(f"Eye_Brow_{side}", arc_on(hc, hr, [(s * 0.2, -1, 0.27), (s * 0.36, -1, 0.31), (s * 0.52, -1, 0.27)],
                                         lift=0.005), hair, radius=0.0085, radii=[0.8, 1.0, 0.65])
        decal(f"Blush_{side}", hc, hr, (s * 0.6, -1, -0.24), (0.036, 0.008, 0.022), blush)
    p, n = surf(hc, hr, (0, -1, -0.17))
    sphere("Nose", p + n * 0.008, (0.024, 0.02, 0.02), skin, seg=14, ring=7)
    # happy open grin: dark mouth, white upper teeth across the top, soft pink lower lip
    p, n = surf(hc, hr, (0.02, -1, -0.43))
    q = facing(n) @ Quaternion((0, 1, 0), -0.08)  # a touch lopsided = cheeky
    half_sphere("Smile_Mouth", p - n * 0.004 + Vector((0, 0, 0.018)), (0.075, 0.014, 0.05), mouth, keep_above=0.0,
                seg=24, ring=10, rot=q @ Quaternion((0, 1, 0), math.pi))
    p2, n2 = surf(hc, hr, (0.02, -1, -0.375))
    sphere("Tooth_Top", p2 + n2 * 0.0035, (0.058, 0.01, 0.016), tooth, seg=20, ring=8, rot=facing(n2))
    p3, n3 = surf(hc, hr, (0.02, -1, -0.565))
    sphere("Smile_LowerLip", p3 + n3 * 0.001, (0.045, 0.008, 0.01), lip, seg=16, ring=6, rot=facing(n3))

    # ---- hair: a shell slightly bigger than the head, shifted up/back, so its crossing
    # with the skull makes a natural hairline (high forehead, short tapered sides, low nape).
    sphere("Hair_Shell", (0, 0.004, 1.685), (0.217, 0.21, 0.234), hair, seg=30, ring=15)
    sphere("Hair_Crown", (0, 0.0, 1.875), (0.14, 0.17, 0.06), hair, seg=20, ring=10)  # fuller top
    import random
    random.seed(11)
    # faux-hawk: a raised central ridge plus a few big flattened, overlapping clumps (one hair mass,
    # not separate beads), swept up and a little forward, with a couple of tips flicking over the forehead.
    sphere("Hair_Ridge", (0, -0.005, 1.885), (0.085, 0.19, 0.07), hair, seg=20, ring=10,
           rot=Quaternion((1, 0, 0), math.radians(10)))
    clumps = [  # (x, y, z of base, forward lean, length, width)
        (0.0, -0.13, 1.86, 0.75, 0.13, 0.075), (-0.06, -0.11, 1.85, 0.6, 0.11, 0.065), (0.06, -0.11, 1.85, 0.6, 0.11, 0.065),
        (0.0, -0.04, 1.91, 0.45, 0.14, 0.08), (-0.07, -0.03, 1.89, 0.35, 0.11, 0.07), (0.07, -0.03, 1.89, 0.35, 0.11, 0.07),
        (0.0, 0.06, 1.91, 0.25, 0.12, 0.08), (-0.075, 0.07, 1.87, 0.2, 0.09, 0.065), (0.075, 0.07, 1.87, 0.2, 0.09, 0.065),
        (0.0, 0.14, 1.86, 0.1, 0.08, 0.07), (-0.11, -0.08, 1.82, 0.4, 0.07, 0.055), (0.11, -0.08, 1.82, 0.4, 0.07, 0.055),
    ]
    for i, (x, y, z, lean, length, w) in enumerate(clumps):
        d = Vector((x * 1.6 + random.uniform(-0.12, 0.12), -lean, 1)).normalized()
        q = Vector((0, 0, 1)).rotation_difference(d) @ Quaternion((0, 0, 1), random.uniform(-0.5, 0.5))
        sphere(f"Hair_Clump_{i}", Vector((x, y, z)) + d * length * 0.45, (w, w * 0.6, length), hair, seg=14, ring=9, rot=q)
        tip = Vector((x, y, z)) + d * length * 1.15 + Vector((random.uniform(-0.01, 0.01), 0, 0))
        sphere(f"Hair_Clump_{i}_Tip", tip, (w * 0.45, w * 0.3, length * 0.5), hair, seg=8, ring=6, rot=q)

    # ---- body: neck, broader shoulders, loose black tee with a big bright original print
    cyl("Neck", (0, 0.0, 1.45), 0.058, 0.12, skin, bevel=0.0, subsurf=1)
    rbox("Torso", (0, 0, 1.09), (0.42, 0.23, 0.66), shirt, bevel=0.1, subsurf=1)
    torus("Torso_Collar", (0, 0.0, 1.42), 0.07, 0.016, shirt, scale=(1.1, 0.95, 1))
    fy = -0.118
    flat("Print_Band", (0, fy, 1.29), (0.165, 0.012, 0.05), yellow)
    for k in range(6):  # bubbly cream 'letters' on the band
        flat(f"Print_Letter_{k}", (-0.135 + 0.054 * k, fy - 0.007, 1.293 + 0.006 * (k % 2)), (0.024, 0.008, 0.033), cream)
    flat("Print_Teal", (-0.05, fy, 1.14), (0.1, 0.012, 0.075), teal)
    flat("Print_Orange", (-0.12, fy - 0.003, 0.99), (0.05, 0.012, 0.07), orange)
    flat("Print_Teal2", (-0.01, fy - 0.003, 0.96), (0.06, 0.012, 0.05), teal)
    flat("Print_Yellow", (0.1, fy - 0.003, 0.98), (0.07, 0.012, 0.07), yellow)
    tube("Print_Bolt", [(0.13, fy - 0.01, 1.24), (0.07, fy - 0.01, 1.13), (0.14, fy - 0.01, 1.12),
                        (0.09, fy - 0.01, 1.03)], yellow, radius=0.016, res=2)
    rbox("Shorts", (0, 0, 0.8), (0.37, 0.22, 0.2), shorts, bevel=0.06, subsurf=1)

    # ---- arms: sleeves grow out of the shoulders; arms angle slightly away; hands a bit big
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        tube(f"Arm_{side}", [(s * 0.2, 0.0, 1.36), (s * 0.27, 0.0, 1.12), (s * 0.305, -0.02, 0.88)], skin, radius=0.052)
        tube(f"Sleeve_{side}", [(s * 0.16, 0.0, 1.37), (s * 0.215, 0.0, 1.33), (s * 0.255, 0.0, 1.2)], shirt,
             radius=0.08, radii=[1.0, 0.95, 0.85])
        sphere(f"Hand_{side}", (s * 0.315, -0.025, 0.8), (0.058, 0.042, 0.08), skin, seg=18, ring=9)
        sphere(f"Hand_{side}_Thumb", (s * 0.29, -0.06, 0.84), (0.018, 0.018, 0.03), skin, seg=10, ring=5,
               rot=Quaternion((0, 1, 0), s * 0.4))
        if s > 0:  # fitness band on his left wrist (+X when facing -Y)
            torus("Hand_R_Watch", (s * 0.302, -0.02, 0.89), 0.053, 0.013, watch, scale=(1, 1, 1.3),
                  rot=(0, math.radians(-8), 0))
            rbox("Hand_R_WatchFace", (s * 0.355, -0.02, 0.895), (0.012, 0.035, 0.05), watch, bevel=0.005, subsurf=0)

    # ---- legs: shorts legs swing with the legs; bare feet with toes
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        tube(f"Leg_{side}", [(s * 0.095, 0.0, 0.78), (s * 0.1, 0.0, 0.42), (s * 0.105, 0.0, 0.09)], skin, radius=0.066)
        tube(f"Leg_{side}_Short", [(s * 0.095, 0.0, 0.8), (s * 0.104, 0.0, 0.46)], shorts, radius=0.098)
        if s > 0:
            flat("Leg_R_Logo", (0.17, -0.078, 0.52), (0.018, 0.006, 0.01), yellow)
        sphere(f"Foot_{side}", (s * 0.11, -0.045, 0.048), (0.072, 0.14, 0.05), skin, seg=20, ring=10)
        for k in range(5):  # k=0 is the big toe, on the inside
            x = s * (0.11 - 0.05 + k * 0.025)
            r = 0.02 if k == 0 else 0.0155 - k * 0.001
            sphere(f"Foot_{side}_Toe{k}", (x, -0.175 + k * 0.008, 0.026), (r, r * 1.1, r), skin, seg=10, ring=5)
    return dict(backdrop="dbe8f5")


def cam_at(yaw, pitch=10, dist=4.6, target=(0, 0, 1.0)):
    cam = bpy.context.scene.camera
    tgt = Vector(target)
    y, p = math.radians(yaw), math.radians(pitch)
    off = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p))) * dist
    cam.location = tgt + off
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-off).to_track_quat("-Z", "Y")


if __name__ == "__main__":
    opts = levi()
    tris = finalize()
    # Bake rotation/scale into each mesh so the joined limb nodes export with a clean transform
    # (the game swings them around their joint; a squashed node transform would skew that).
    bpy.ops.object.select_all(action="DESELECT")
    for o in toykit.STATE["coll"].objects:
        if o.type == "MESH":
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    studio(backdrop=opts["backdrop"], target=(0, 0, 1.0), dist=4.6, yaw=28, pitch=10, lens=60)
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = 640
    print("TRIS giant", tris)
    out = os.path.abspath(os.path.join(ROOT, "assets", "giant"))
    render_and_save(os.path.join(out, "giant.png"), os.path.abspath(os.path.join(ROOT, "art", "characters", "giant.blend")))
    cam_at(90)
    sc.render.filepath = os.path.join(out, "giant_side.png")
    bpy.ops.render.render(write_still=True)
    print("DONE giant")
