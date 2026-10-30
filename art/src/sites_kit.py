# Infinity Stone challenge sites: big set pieces for the Avengers missions.
# Run: blender --background --python art/src/sites_kit.py [-- interior|close]
# Exports assets/sites/sites.glb (one top-level node per piece) and a lineup render
# at art/renders/sites_kit.png (+ art/renders/sites_kit_interior.png, Sanctum inside).
#
# Units are world metres in game (player ~0.53 tall, jumps ~1.3). Built Z-up in Blender
# (front = Blender -Y = Godot +Z). Every piece's origin is the centre of its footprint at
# floor level (HoverPlatform: deck top centre). Key heights are exact; see HEIGHTS below.
#
# Collision: every piece has convex children "<Piece>_colN-convcolonly" (boxes, wedges,
# prisms) that Godot turns into StaticBody3D + CollisionShape3D on import.
#
# Materials follow the city kit naming so city.gd kit_mat() can swap textures by prefix:
# Concrete* -> concrete, Brick* -> brick, Plaster*/Trim* -> plaster, Rust* -> rust (base
# colour = tint). Glow* materials carry emission. Others are plain colour x vertex colour.
import bpy, bmesh, math, os, random, sys
from mathutils import Vector, Matrix, Euler, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import city_kit as ck
from city_kit import (t_box, t_prism, t_cyl, t_bar, t_tube, t_torus, t_quad, t_panel, TR, side_M, clamp, sstep,
                      jagged_slab)

ROOT = ck.ROOT
OUT = os.path.join(ROOT, "assets", "sites")
RENDERS = ck.RENDERS
TEX = ck.TEX
os.makedirs(OUT, exist_ok=True)

# name: (base colour, roughness, metallic, emission colour, emission strength, alpha)
MAT_DEFS = {
    "Concrete":        ((0.8, 0.84, 0.88, 1), 0.92, 0.0),
    "ConcreteDark":    ((0.42, 0.43, 0.47, 1), 0.9, 0.0),
    "ConcreteRock":    ((0.62, 0.58, 0.55, 1), 0.95, 0.0),
    "ConcreteTemple":  ((0.72, 0.72, 0.62, 1), 0.95, 0.0),
    "ConcreteVormir":  ((0.5, 0.45, 0.62, 1), 0.95, 0.0),
    "Brick":           ((0.78, 0.5, 0.42, 1), 0.9, 0.0),
    "PlasterSanctum":  ((0.62, 0.36, 0.28, 1), 0.9, 0.0),
    "PlasterCeiling":  ((0.86, 0.8, 0.68, 1), 0.9, 0.0),
    "TrimStone":       ((0.86, 0.79, 0.66, 1), 0.85, 0.0),
    "TrimCream":       ((0.93, 0.9, 0.82, 1), 0.7, 0.0),
    "RustChitauri":    ((0.5, 0.52, 0.58, 1), 0.6, 0.5),
    "MetalDark":       ((0.09, 0.09, 0.11, 1), 0.38, 0.85),
    "MetalChitauri":   ((0.2, 0.19, 0.17, 1), 0.45, 0.8),
    "Rebar":           ((0.25, 0.14, 0.09, 1), 0.7, 0.6),
    "Glass":           ((0.04, 0.055, 0.065, 1), 0.08, 0.0),
    "Interior":        ((0.035, 0.033, 0.038, 1), 0.95, 0.0),
    "Wood":            ((0.2, 0.11, 0.06, 1), 0.6, 0.0),
    "WoodFloor":       ((0.34, 0.2, 0.11, 1), 0.55, 0.0),
    "Gold":            ((0.85, 0.62, 0.25, 1), 0.3, 1.0),
    "Book":            ((1, 1, 1, 1), 0.8, 0.0),
    "Rug":             ((0.5, 0.07, 0.06, 1), 1.0, 0.0),
    "RugGold":         ((0.75, 0.52, 0.2, 1), 1.0, 0.0),
    "RugBlue":         ((0.08, 0.12, 0.3, 1), 1.0, 0.0),
    "Cloak":           ((0.6, 0.05, 0.04, 1), 0.85, 0.0),
    "Candle":          ((0.95, 0.9, 0.78, 1), 0.7, 0.0),
    "GlassCase":       ((0.7, 0.85, 0.9, 1), 0.05, 0.0, None, 0.0, 0.22),
    "GlowRed":         ((1.0, 0.1, 0.05, 1), 0.4, 0.0, (1.0, 0.06, 0.02), 6.0),
    "GlowCyan":        ((0.4, 0.85, 1.0, 1), 0.4, 0.0, (0.25, 0.75, 1.0), 6.0),
    "GlowAmber":       ((1.0, 0.7, 0.3, 1), 0.4, 0.0, (1.0, 0.55, 0.15), 5.0),
    "GlowEmber":       ((1.0, 0.35, 0.1, 1), 0.6, 0.0, (1.0, 0.28, 0.05), 3.0),
    "GlowViolet":      ((0.7, 0.3, 1.0, 1), 0.4, 0.0, (0.62, 0.18, 1.0), 6.0),
    "GlowGreen":       ((0.35, 1.0, 0.45, 1), 0.4, 0.0, (0.2, 1.0, 0.35), 5.0),
    "GlowSeal":        ((1.0, 0.85, 0.6, 1), 0.3, 0.0, (1.0, 0.72, 0.38), 1.6),
    "GlowWindow":      ((1.0, 0.75, 0.4, 1), 0.3, 0.0, (1.0, 0.62, 0.3), 1.4),
    "GlassDay":        ((0.6, 0.7, 0.8, 1), 0.2, 0.0, (0.55, 0.68, 0.85), 0.9),
    "GooStain":        ((0.5, 0.03, 0.02, 1), 0.3, 0.0, (0.9, 0.05, 0.02), 1.5),
}
mats = {}


def mat(name):
    if name in mats:
        return mats[name]
    d = MAT_DEFS[name]
    col, rough, metal = d[:3]
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if len(d) > 3 and d[3]:
        b.inputs["Emission Color"].default_value = (*d[3], 1)
        b.inputs["Emission Strength"].default_value = d[4]
    if len(d) > 5:
        b.inputs["Alpha"].default_value = d[5]
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    mats[name] = m
    return m


class SPiece(ck.Piece):
    """City-kit piece builder without the z >= 0 clamp, using this file's materials."""

    def finish(self):
        bm = self.bm
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(mat(m))
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.collection.objects.link(ob)
        if "Col" in me.color_attributes:
            me.color_attributes.active_color = me.color_attributes["Col"]
            me.color_attributes.render_color_index = me.color_attributes.find("Col")
        return ob


# ---------------------------------------------------------------- collision
class Cols:
    def __init__(self, name):
        self.name = name
        self.objs = []

    def hull(self, pts):
        bm = bmesh.new()
        vs = [bm.verts.new(Vector(p)) for p in pts]
        res = bmesh.ops.convex_hull(bm, input=vs)
        dead = list({v for v in res["geom_interior"] + res["geom_unused"] if isinstance(v, bmesh.types.BMVert)})
        if dead:
            bmesh.ops.delete(bm, geom=dead, context="VERTS")
        n = "%s_col%d-convcolonly" % (self.name, len(self.objs) + 1)
        me = bpy.data.meshes.new(n)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(n, me)
        bpy.context.collection.objects.link(ob)
        ob.display_type = "WIRE"
        self.objs.append(ob)
        return ob

    def box(self, x0, y0, z0, x1, y1, z1, M=None):
        M = M if M is not None else Matrix.Identity(4)
        return self.hull([M @ Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])

    def attach(self, parent):
        for o in self.objs:
            o.parent = parent
            o.hide_render = True
        return self.objs


# ---------------------------------------------------------------- extra primitives
def t_rock(rng, sx, sy, sz, sub=1, seed=None, rough=0.28, flat_bottom=True):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    off = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    for v in bm.verts:
        d = v.co.normalized()
        k = 1 + rough * noise.noise(d * 1.7 + off) + 0.5 * rough * noise.noise(d * 3.9 + off)
        p = d * k
        if flat_bottom:
            p.z = max(p.z, -0.25)
        v.co = Vector((p.x * sx, p.y * sy, p.z * sz))
    for f in bm.faces:
        f.smooth = False
    return bm


def t_loft(rings, cap0=True, cap1=True, smooth=False):
    """Rings of equal length (lists of 3D points, CCW seen from above) joined bottom to top."""
    bm = bmesh.new()
    vr = [[bm.verts.new(Vector(p)) for p in r] for r in rings]
    n = len(rings[0])
    for a, b in zip(vr, vr[1:]):
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new([a[i], a[j], b[j], b[i]])
            f.smooth = smooth
    if cap0:
        bm.faces.new(vr[0][::-1])
    if cap1:
        bm.faces.new(vr[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def t_poly(pts2, z0, z1):
    """Vertical prism from a 2D outline."""
    return t_prism([(x, y, z0) for x, y in pts2], (0, 0, z1 - z0))


def t_octa(r, h):
    bm = bmesh.new()
    top, bot = bm.verts.new((0, 0, h)), bm.verts.new((0, 0, -h))
    ring = [bm.verts.new((r * math.cos(a * math.pi / 2), r * math.sin(a * math.pi / 2), 0)) for a in range(4)]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new([ring[i], ring[j], top])
        bm.faces.new([ring[j], ring[i], bot])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def t_sq_ring(cx, cz, half, r, y0, y1, seg=32):
    """Square wall patch (front frame, xz plane) with a round hole: faces 0 = front (y0, -Y),
    1 = back (y1), 2 = round reveal."""
    bm = bmesh.new()
    fo, fi, bo, bi = [], [], [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        dx, dz = math.cos(a), math.sin(a)
        s = half / max(abs(dx), abs(dz))
        for lst, y, rr in ((fo, y0, s), (fi, y0, r), (bo, y1, s), (bi, y1, r)):
            lst.append(bm.verts.new((cx + dx * rr, y, cz + dz * rr)))
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new([fo[i], fi[i], fi[j], fo[j]]).material_index = 0
        bm.faces.new([bo[j], bi[j], bi[i], bo[i]]).material_index = 1
        bm.faces.new([fi[i], bi[i], bi[j], fi[j]]).material_index = 2
    for f in bm.faces:
        want = {0: Vector((0, -1, 0)), 1: Vector((0, 1, 0))}.get(f.material_index)
        if want is not None and f.normal.dot(want) < 0:
            f.normal_flip()
        if f.material_index == 2:
            c = f.calc_center_median()
            if (Vector((cx, c.y, cz)) - c).dot(f.normal) < 0:
                f.normal_flip()
    return bm


def t_disc(r, seg, y, facing):
    """Flat disc in the xz plane at y, facing -Y (facing=-1) or +Y (facing=1)."""
    bm = bmesh.new()
    vs = [bm.verts.new((r * math.cos(2 * math.pi * i / seg), y, r * math.sin(2 * math.pi * i / seg)))
          for i in range(seg)]
    f = bm.faces.new(vs)
    if f.normal.y * facing < 0:
        f.normal_flip()
    return bm


def t_quad_facing(pts, facing):
    bm = t_quad(pts)
    bm.faces.ensure_lookup_table()
    f = bm.faces[0]
    f.normal_update()
    if f.normal.dot(Vector(facing)) < 0:
        f.normal_flip()
    return bm


def g_noise(base=1.0, ground=0.0, k=1.9):
    def g(p, n):
        v = base * (0.88 + 0.12 * noise.noise(p * k))
        if n.z < -0.5:
            v *= 0.72
        if ground:
            v *= 1 - ground * (1 - sstep(p.z / 0.6))
        return v
    return g


def arc_pts(c, R, a0, a1, n, y):
    return [Vector((c[0] + R * math.cos(a0 + (a1 - a0) * i / n), y, c[1] + R * math.sin(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


# ================================================================ 1. Ultron tower
def ultron_tower():
    rng = random.Random(101)
    P = SPiece("UltronTower", grime=g_noise(1.0, 0.45))
    C = Cols("UltronTower")
    TOP = 6.0
    # concrete core + roof slab (roof surface exactly at 6.0)
    P.box(-1.88, -1.88, 0, 1.88, 1.88, 5.78, "ConcreteDark")
    P.box(-1.97, -1.97, 5.78, 1.97, 1.97, TOP, "ConcreteDark", bevel=0.02)
    # steel corner columns (flush to the roof) and two broken stubs above it
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.box(sx * 1.72, sy * 1.72, 0, sx * 2.0, sy * 2.0, TOP, "MetalDark", 0.8, bevel=0.012)
    stubs = [(1, 1, 6.55), (-1, 1, 6.3)]
    for sx, sy, h in stubs:
        x0, x1 = sorted((sx * 1.72, sx * 2.0))
        y0, y1 = sorted((sy * 1.72, sy * 2.0))
        P.add(t_prism([(x0, y0, TOP), (x1, y0, TOP), (x1, y1, TOP), (x0, y1, TOP)], (0, 0, h - TOP)), None,
              "MetalDark", 0.75)
        P.add(t_prism([(x0, y0, h), (x1, y0, h), (x1, y1, h - 0.12), (x0, y1, h - 0.06)], (0, 0, 0.001)), None,
              "MetalDark", 0.7)
        P.add(t_cyl(0.07, 0.08, 8), TR(((x0 + x1) / 2, (y0 + y1) / 2, h - 0.04)), "GlowRed")
        C.box(x0, y0, TOP, x1, y1, h)
    # floor bands
    for z in (1.5, 3.0, 4.5):
        P.box(-1.97, -1.97, z - 0.05, 1.97, 1.97, z + 0.05, "MetalDark", 0.6)
    # cladding panels, Ultron face, red light strips, per side
    rows = [(0.1, 1.45), (1.55, 2.95), (3.05, 4.45), (4.55, 5.75)]
    colsu = [(-1.72, -0.573), (-0.573, 0.573), (0.573, 1.72)]
    for k in range(4):
        M = side_M(k)
        for r, (z0, z1) in enumerate(rows):
            for c, (u0, u1) in enumerate(colsu):
                if k == 0 and r == 3:
                    continue   # face plate
                if k == 0 and r == 2 and c == 1:
                    continue   # doorway behind the balcony
                roll = rng.random()
                if roll < 0.16:
                    # missing panel: exposed concrete, burn and rebar
                    P.box(u0 + 0.05, -1.9, z0 + 0.05, u1 - 0.05, -1.88, z1 - 0.05, "ConcreteDark", 0.55, M=M)
                    for i in range(3):
                        ck.rebar_spray(P, rng, (rng.uniform(u0 + 0.2, u1 - 0.2), -1.9, rng.uniform(z0 + 0.2, z1 - 0.2)),
                                       (0, -1, 0), 2, (0.08, 0.18), 0.1, M=M, droop=0.3)
                    continue
                tint = rng.uniform(0.75, 1.1)
                if roll < 0.3:
                    # hanging panel, pivoting off its top edge
                    a = rng.uniform(0.1, 0.22) * rng.choice((-1, 1))
                    hinge = TR(((u0 + u1) / 2, -1.9, z1 - 0.04), (0, a * 0.3, 0)) @ TR(rot=(-abs(a), 0, 0))
                    P.add(t_box(-(u1 - u0) / 2 + 0.04, -0.07, -(z1 - z0) + 0.1, (u1 - u0) / 2 - 0.04, 0, 0, 0.01),
                          M @ hinge, "MetalDark", tint)
                    P.box(u0 + 0.05, -1.9, z0 + 0.05, u1 - 0.05, -1.88, z1 - 0.05, "ConcreteDark", 0.5, M=M)
                    continue
                P.box(u0 + 0.035, -1.965, z0 + 0.035, u1 - 0.035, -1.88, z1 - 0.035, "MetalDark", tint, bevel=0.01, M=M)
                # raised rib + bolt strip for a machined look
                zm = z0 + (z1 - z0) * rng.choice((0.3, 0.7))
                P.box(u0 + 0.12, -1.985, zm - 0.03, u1 - 0.12, -1.96, zm + 0.03, "MetalDark", tint * 1.3, M=M)
                if roll > 0.85:
                    # cracked: a jagged dent scar
                    P.box(u0 + 0.2, -1.97, z0 + 0.25, u0 + 0.5, -1.96, z0 + 0.32, "Interior", 1.0, M=M)
        # vertical red strips in the gaps between panel columns (broken into runs)
        for u in (-0.573, 0.573):
            z = 0.25
            while z < 5.7:
                L = rng.uniform(0.6, 2.2)
                z1 = min(z + L, 5.7)
                P.box(u - 0.022, -1.945, z, u + 0.022, -1.9, z1, "GlowRed", M=M)
                z = z1 + rng.uniform(0.1, 0.6)
        # top strip just under the roof slab
        P.box(-1.72, -1.95, 5.68, 1.72, -1.9, 5.72, "GlowRed", M=M)
        # ground-floor lights
        P.box(-1.72, -1.95, 0.12, 1.72, -1.9, 0.15, "GlowRed", M=M)
    # Ultron face plate (front, top row)
    P.box(-1.68, -1.97, 4.6, 1.68, -1.88, 5.72, "MetalDark", 0.75, bevel=0.015)
    for s in (-1, 1):
        # brow ridge
        brow = [(s * 0.15, 5.42), (s * 1.45, 5.62), (s * 1.5, 5.5), (s * 0.2, 5.3)]
        P.add(t_prism([(u, -1.97, z) for u, z in brow], (0, -0.06, 0)), None, "MetalDark", 1.2)
        # angular eye slit (glowing), inner end lower
        eye = [(s * 0.3, 5.2), (s * 1.22, 5.38), (s * 1.18, 5.25), (s * 0.36, 5.08)]
        P.add(t_prism([(u, -1.975, z) for u, z in eye], (0, -0.04, 0)), None, "GlowRed")
        # cheek plates
        cheek = [(s * 0.35, 4.98), (s * 1.3, 5.15), (s * 1.45, 4.7), (s * 0.55, 4.66)]
        P.add(t_prism([(u, -1.97, z) for u, z in cheek], (0, -0.04, 0)), None, "MetalDark", 1.15)
    # mouth grille
    for i in range(7):
        u = -0.3 + i * 0.1
        P.box(u - 0.018, -2.0, 4.7, u + 0.018, -1.96, 4.95 - abs(u) * 0.3, "GlowRed")
    # --- broken balcony ledge at exactly 3.0 on the front: 0.8 deep from the wall plane (y=-2.0)
    BL = 3.0
    slab, pts = jagged_slab(rng, -0.8, 0.8, -2.92, -1.9, 0.25, "y0", n=6, amp=0.16)
    P.add(slab, TR((0, 0, BL - 0.25)), "ConcreteDark", 0.85)
    for (x, y) in pts[2:-1:2]:
        ck.rebar_spray(P, rng, (x, y + 0.03, BL - 0.1), (0, -1, -0.2), 2, (0.08, 0.2), 0.05, droop=0.6)
    # steel brackets under the ledge
    for x in (-0.65, 0.65):
        P.add(t_bar((x, -2.0, 2.15), (x, -2.7, BL - 0.27), 0.04, sides=4, smooth=False), None, "MetalDark", 0.8)
    # bent railing: one standing post, the rail drooping off the broken edge
    P.add(t_bar((-0.74, -2.75, BL), (-0.74, -2.75, BL + 0.55), 0.025, sides=5), None, "MetalDark", 0.9)
    P.add(t_tube([(-0.74, -2.75, BL + 0.55), (-0.2, -2.8, BL + 0.5), (0.25, -2.95, BL + 0.2), (0.4, -3.05, BL - 0.25)],
                 [0.022] * 4, 5), None, "MetalDark", 0.9)
    # doorway behind the ledge: dark opening with red frame
    P.box(-0.5, -1.89, BL, 0.5, -1.86, 4.4, "Interior")
    P.box(-0.56, -1.96, BL, -0.5, -1.86, 4.42, "MetalDark", 0.9)
    P.box(0.5, -1.96, BL, 0.56, -1.86, 4.42, "MetalDark", 0.9)
    P.box(-0.56, -1.96, 4.4, 0.56, -1.86, 4.46, "MetalDark", 0.9)
    P.box(-0.5, -1.92, 4.34, 0.5, -1.88, 4.37, "GlowRed")
    P.add(t_cyl(0.06, 0.02, 10), TR((0.0, -1.875, 3.9), (math.pi / 2, 0, 0)), "GlowRed")
    C.box(-0.8, -2.8, BL - 0.25, 0.8, -1.95, BL)
    # sealed blast door at the base (front)
    P.box(-0.6, -1.99, 0.0, 0.6, -1.9, 1.3, "MetalDark", 1.25, bevel=0.01)
    P.box(-0.02, -2.0, 0.05, 0.02, -1.98, 1.25, "GlowRed")
    for z in (0.35, 0.7, 1.05):
        P.box(-0.55, -2.0, z, 0.55, -1.985, z + 0.04, "MetalDark", 1.5)
    # roof: rubble at the corners (centre 2x2 clear), broken antenna mast, vent box
    for cx, cy in ((-1.35, -1.4), (1.4, -1.3), (-1.45, 1.35), (1.3, 1.45)):
        ck.rubble_chunks(P, rng, cx, cy, 0.42, 7, z=TOP, mats=("ConcreteDark", "ConcreteDark", "MetalDark"),
                         size=(0.08, 0.26), tint=(0.6, 0.95))
    P.add(t_bar((1.55, 1.55, TOP), (1.6, 1.4, TOP + 1.3), 0.035, 0.02, sides=5), None, "MetalDark", 0.8)
    P.add(t_bar((1.6, 1.4, TOP + 1.3), (1.2, 1.0, TOP + 1.05), 0.02, sides=4), None, "MetalDark", 0.8)
    P.add(t_cyl(0.05, 0.06, 8), TR((1.6, 1.4, TOP + 1.3)), "GlowRed")
    P.box(-1.7, 1.0, TOP, -1.15, 1.7, TOP + 0.35, "MetalDark", 0.7, bevel=0.02)
    P.box(-1.65, 1.05, TOP + 0.35, -1.2, 1.65, TOP + 0.38, "GlowRed")
    # a bent beam sticking out of the roof edge
    P.add(t_box(-0.06, -0.06, 0, 0.06, 0.06, 1.1), TR((-1.85, -1.6, TOP - 0.1), (0.35, -0.5, 0.3)), "MetalDark", 0.8)
    # base rubble (stays low)
    for cx, cy in ((-2.3, -2.2), (2.4, -1.6), (2.2, 2.3), (-2.4, 1.8)):
        ck.rubble_chunks(P, rng, cx, cy, 0.55, 9, z=0.0, mats=("ConcreteDark", "MetalDark", "Concrete"),
                         size=(0.08, 0.3), tint=(0.55, 0.95))
    # main collision block: sheer walls, roof top at 6.0
    C.box(-2.0, -2.0, 0, 2.0, 2.0, TOP)
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ 2. Chitauri hover platform
def hover_platform():
    rng = random.Random(202)

    def g(p, n):
        v = 0.85 + 0.15 * noise.noise(p * 2.3)
        if n.z < -0.5:
            v *= 0.7
        return v
    P = SPiece("HoverPlatform", grime=g)
    C = Cols("HoverPlatform")
    H = 1.5
    ch = 0.16

    def octo(h, c):
        return [(h - c, -h), (h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c), (-h + c, -h)]
    # base slab and edge band
    P.add(t_poly(octo(H - 0.02, ch), -0.26, -0.04), None, "MetalChitauri", 0.85)
    P.add(t_poly(octo(H, ch), -0.2, -0.1), None, "RustChitauri", 0.7)
    # glowing edge strip all round
    P.add(t_poly(octo(H + 0.012, ch + 0.004), -0.165, -0.135), None, "GlowCyan")
    # top plates (four quadrants) with glowing seams between them; top exactly at 0
    gap = 0.035
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts = [(sx * gap, sy * gap), (sx * (H - 0.03), sy * gap), (sx * (H - 0.03), sy * (H - 0.03 - ch)),
                   (sx * (H - 0.03 - ch), sy * (H - 0.03)), (sx * gap, sy * (H - 0.03))]
            if sx * sy < 0:
                pts = pts[::-1]
            P.add(t_poly(pts, -0.06, 0.0), None, "RustChitauri", rng.uniform(0.85, 1.05))
    P.box(-gap, -H + 0.05, -0.045, gap, H - 0.05, -0.02, "GlowCyan")
    P.box(-H + 0.05, -gap, -0.045, H - 0.05, gap, -0.02, "GlowCyan")
    # centre emblem disc + glowing ring groove
    P.add(t_cyl(0.42, 0.065, 24), TR((0, 0, -0.065)), "MetalChitauri", 1.0)
    P.add(t_cyl(0.5, 0.04, 24), TR((0, 0, -0.06)), "GlowCyan")
    # angular chevron inlays (flush, slightly sunk)
    for k in range(4):
        M = Matrix.Rotation(k * math.pi / 2 + math.pi / 4, 4, "Z")
        P.add(t_prism([(0.62, -0.05, -0.012), (1.25, -0.05, -0.012), (1.32, 0, -0.012), (1.25, 0.05, -0.012),
                       (0.62, 0.05, -0.012)], (0, 0, 0.0115)), M, "MetalChitauri", 0.55)
    # hull underneath: tapering octagon
    rings = [[(x * 0.98, y * 0.98, -0.26) for x, y in octo(H, ch)],
             [(x * 0.62, y * 0.62, -0.62) for x, y in octo(H, ch)],
             [(x * 0.38, y * 0.38, -0.82) for x, y in octo(H, ch)]]
    P.add(t_loft(rings, False, True), None, "MetalChitauri", 0.8)
    # ribs on the hull
    for k in range(8):
        a = k * math.pi / 4 + math.pi / 8
        d = Vector((math.cos(a), math.sin(a), 0))
        p0, p1 = d * 1.3 + Vector((0, 0, -0.27)), d * 0.5 + Vector((0, 0, -0.84))
        P.add(t_bar(p0, p1, 0.05, 0.035, sides=4, smooth=False), None, "RustChitauri", 0.6)
    # central thruster
    P.add(t_cyl(0.36, 0.14, 16, r2=0.3), TR((0, 0, -0.96)), "MetalChitauri", 0.7)
    P.add(t_torus(0.3, 0.035, 16, 6), TR((0, 0, -0.97)), "GlowCyan")
    P.add(t_cyl(0.27, 0.02, 16), TR((0, 0, -0.985)), "GlowCyan")
    P.add(t_cyl(0.22, 0.25, 12, r2=0.0), TR((0, 0, -0.985), (math.pi, 0, 0)), "GlowCyan")
    # corner engine pods
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        d = Vector((math.cos(a), math.sin(a), 0))
        c = d * 1.42
        P.add(t_cyl(0.22, 0.42, 12, r2=0.26), TR((c.x, c.y, -0.66)), "MetalChitauri", 0.9)
        P.add(t_cyl(0.27, 0.06, 12), TR((c.x, c.y, -0.3)), "RustChitauri", 0.8)
        P.add(t_torus(0.2, 0.03, 12, 5), TR((c.x, c.y, -0.67)), "GlowCyan")
        P.add(t_cyl(0.17, 0.015, 12), TR((c.x, c.y, -0.685)), "GlowCyan")
        P.add(t_cyl(0.15, 0.18, 10, r2=0.0), TR((c.x, c.y, -0.685), (math.pi, 0, 0)), "GlowCyan")
        P.add(t_bar(c * 0.55 + Vector((0, 0, -0.55)), c * 0.95 + Vector((0, 0, -0.5)), 0.05, sides=4, smooth=False),
              None, "MetalChitauri", 0.7)
        # swept-back prongs on the sides (alien silhouette), below deck level
        a2 = k * math.pi / 2
        e = Vector((math.cos(a2), math.sin(a2), 0))
        t = Vector((-e.y, e.x, 0))
        for s in (-1, 1):
            P.add(t_tube([e * 1.45 + t * s * 0.35 + Vector((0, 0, -0.18)),
                          e * 1.75 + t * s * 0.45 + Vector((0, 0, -0.28)),
                          e * 1.95 + t * s * 0.62 + Vector((0, 0, -0.5))], [0.06, 0.04, 0.012], 4, smooth=False),
                  None, "MetalChitauri", 0.9)
    C.box(-H, -H, -0.26, H, H, 0.0)
    C.hull([(x * 0.98, y * 0.98, -0.26) for x, y in octo(H, ch)] + [(x * 0.38, y * 0.38, -0.82) for x, y in octo(H, ch)])
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ 3. Goo pool rim + island
R_IN, R_OUT, RIM = 7.0, 8.5, 0.35


def goo_rim():
    rng = random.Random(303)

    def g(p, n):
        v = 0.85 + 0.15 * noise.noise(p * 1.3)
        r = math.hypot(p.x, p.y)
        if n.z < -0.5:
            v *= 0.7
        v *= 0.6 + 0.4 * sstep((p.z + 0.4) / 0.6)
        return v

    def stain(p):
        r = math.hypot(p.x, p.y)
        if r < R_IN + 0.15 and p.z < 0.2:
            k = 1 - clamp((p.z + 0.1) / 0.3)
            return (1.0, 1 - 0.65 * k, 1 - 0.7 * k)
        return 1.0
    P = SPiece("GooPoolRim", grime=g)
    C = Cols("GooPoolRim")
    N = 26
    for i in range(N):
        a0 = 2 * math.pi * i / N + 0.006
        a1 = 2 * math.pi * (i + 1) / N - 0.006
        sub = 4
        inner, outer = [], []
        for s in range(sub + 1):
            a = a0 + (a1 - a0) * s / sub
            ri = R_IN + (rng.uniform(0.0, 0.1) if 0 < s < sub else 0.02)
            ro = R_OUT - (rng.uniform(0.0, 0.12) if 0 < s < sub else 0.04)
            inner.append((ri * math.cos(a), ri * math.sin(a)))
            outer.append((ro * math.cos(a), ro * math.sin(a)))
        pts = outer + inner[::-1]
        rocky = rng.random() < 0.3
        m = "ConcreteRock" if rocky else "Concrete"
        sink = 0.0 if rng.random() < 0.7 else rng.uniform(0.0, 0.02)
        P.add(t_poly(pts, -0.45, RIM - sink), None, m, (lambda p, t=rng.uniform(0.7, 1.0): (
            tuple(c * t for c in stain(p)) if isinstance(stain(p), tuple) else t * stain(p))))
        # top: worn edge chamfer strip + crack lines
        if not rocky:
            amid = (a0 + a1) / 2
            for c in range(rng.randint(1, 2)):
                aa = amid + rng.uniform(-0.06, 0.06)
                r0, r1 = R_IN + rng.uniform(0.1, 0.4), R_OUT - rng.uniform(0.1, 0.5)
                d = Vector((math.cos(aa), math.sin(aa), 0))
                t = Vector((-d.y, d.x, 0)) * 0.012
                p0, p1 = d * r0, d * r1 + t * rng.uniform(-8, 8)
                P.add(t_quad_facing([p0 - t + Vector((0, 0, RIM + 0.003)), p1 - t + Vector((0, 0, RIM + 0.003)),
                                     p1 + t + Vector((0, 0, RIM + 0.003)), p0 + t + Vector((0, 0, RIM + 0.003))],
                                    (0, 0, 1)), None, "Interior")
        # glowing goo stain band on the inner face
        aa0, aa1 = a0 + 0.01, a1 - 0.01
        ri = R_IN - 0.012
        q = [(ri * math.cos(aa0), ri * math.sin(aa0), -0.25), (ri * math.cos(aa1), ri * math.sin(aa1), -0.25),
             (ri * math.cos(aa1), ri * math.sin(aa1), 0.02 + rng.uniform(0, 0.06)),
             (ri * math.cos(aa0), ri * math.sin(aa0), 0.02 + rng.uniform(0, 0.06))]
        mid = Vector(((q[0][0] + q[1][0]) / 2, (q[0][1] + q[1][1]) / 2, 0))
        P.add(t_quad_facing(q, -mid), None, "GooStain")
        # collision: exact wedge hull of the segment (chords), full gap-free ring
        b0, b1 = 2 * math.pi * i / N, 2 * math.pi * (i + 1) / N
        hp = []
        for a in (b0, (b0 + b1) / 2, b1):
            for r in (R_IN, R_OUT / math.cos(math.pi / N / 2)):
                for z in (-0.45, RIM):
                    hp.append((r * math.cos(a), r * math.sin(a), z))
        C.hull(hp)
        # decoration: rebar on the inner edge, rocks outside, chunks in the goo
        if rng.random() < 0.35:
            am = (a0 + a1) / 2
            d = Vector((math.cos(am), math.sin(am), 0))
            ck.rebar_spray(P, rng, d * (R_IN + 0.05) + Vector((0, 0, RIM - 0.08)), -d + Vector((0, 0, 0.3)), 2,
                           (0.15, 0.35), 0.25, droop=0.4)
        for j in range(rng.randint(1, 3)):
            am = rng.uniform(a0, a1)
            d = Vector((math.cos(am), math.sin(am), 0))
            s = rng.uniform(0.12, 0.3)
            P.add(t_rock(rng, s * 1.4, s, s * 0.8), TR((*(d * (R_OUT + s * 0.7)), 0.0), (0, 0, rng.uniform(0, 6))),
                  "ConcreteRock", rng.uniform(0.6, 0.9))
        if rng.random() < 0.3:
            am = rng.uniform(a0, a1)
            d = Vector((math.cos(am), math.sin(am), 0))
            s = rng.uniform(0.18, 0.35)
            P.add(t_box(-s, -s * 0.6, -0.4, s, s * 0.6, 0.06), TR((*(d * (R_IN - rng.uniform(0.4, 0.9))), 0),
                                                                  (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3),
                                                                   rng.uniform(0, 6))), "Concrete", 0.55)
    ob = P.finish()
    C.attach(ob)
    return ob


def goo_island():
    rng = random.Random(304)
    P = SPiece("GooIsland", grime=g_noise(1.0, 0.0, 1.5))
    C = Cols("GooIsland")
    seg = 18
    off = Vector((3.1, 7.7, 1.2))
    rings = []
    for z, r, amp in ((-0.45, 1.98, 0.14), (-0.1, 1.86, 0.12), (0.18, 1.72, 0.08), (0.3, 1.64, 0.03), (RIM, 1.6, 0.0)):
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            d = Vector((math.cos(a), math.sin(a), 0))
            rr = r + amp * noise.noise(d * 2.2 + off + Vector((0, 0, z * 3)))
            ring.append(Vector((d.x * rr, d.y * rr, z)))
        rings.append(ring)
    P.add(t_loft(rings, True, True), None, "ConcreteRock",
          lambda p: (1.0, 0.55, 0.5) if p.z < 0.0 else 1.0)
    # cracked flagstone top (flush), a few pebbles at the very edge
    for i in range(5):
        a = rng.uniform(0, 2 * math.pi)
        d = Vector((math.cos(a), math.sin(a), 0))
        t = Vector((-d.y, d.x, 0)) * 0.01
        p0, p1 = d * rng.uniform(0.3, 0.8), d * rng.uniform(1.3, 1.55)
        P.add(t_quad_facing([p0 - t + Vector((0, 0, RIM + 0.003)), p1 - t + Vector((0, 0, RIM + 0.003)),
                             p1 + t + Vector((0, 0, RIM + 0.003)), p0 + t + Vector((0, 0, RIM + 0.003))], (0, 0, 1)),
              None, "Interior")
    for i in range(7):
        a = rng.uniform(0, 2 * math.pi)
        s = rng.uniform(0.07, 0.16)
        P.add(t_rock(rng, s * 1.3, s, s * 0.7), TR((1.45 * math.cos(a), 1.45 * math.sin(a), RIM)), "ConcreteRock",
              rng.uniform(0.6, 0.85))
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        r = 1.95 - 0.012
    C.hull([p for p in rings[0]] + [Vector((v.x, v.y, RIM)) for v in rings[-1]])
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ 4. Turret (base + Head + Muzzle)
HEAD_Z = 0.78
MUZZLE_Y = -0.7


def turret():
    rng = random.Random(404)
    P = SPiece("Turret", grime=ck.grime_prop(0.3))
    C = Cols("Turret")
    P.add(t_cyl(0.36, 0.08, 8, smooth=False), None, "MetalChitauri", 0.8)
    P.add(t_cyl(0.28, 0.06, 8, smooth=False), TR((0, 0, 0.08)), "RustChitauri", 0.8)
    for k in range(3):
        a = k * 2 * math.pi / 3 + math.pi / 6
        d = Vector((math.cos(a), math.sin(a), 0))
        P.add(t_tube([d * 0.12 + Vector((0, 0, 0.42)), d * 0.38 + Vector((0, 0, 0.22)), d * 0.5 + Vector((0, 0, 0.0))],
                     [0.06, 0.05, 0.03], 4, smooth=False), None, "MetalChitauri", 0.9)
        P.add(t_cyl(0.025, 0.03, 6), TR((*(d * 0.3), 0.27)), "GlowCyan")
    P.add(t_cyl(0.12, 0.47, 10, r2=0.1), TR((0, 0, 0.12)), "MetalChitauri", 0.75)
    P.add(t_torus(0.13, 0.025, 12, 5), TR((0, 0, 0.42)), "GlowCyan")
    P.add(t_cyl(0.22, 0.07, 12), TR((0, 0, 0.56)), "RustChitauri", 0.85)
    P.add(t_torus(0.2, 0.02, 14, 4), TR((0, 0, 0.63)), "GlowCyan")
    C.box(-0.32, -0.32, 0, 0.32, 0.32, 0.64)
    base = P.finish()
    C.attach(base)
    # head, local to its pivot
    Hd = SPiece("Head", grime=lambda p, n: (0.88 + 0.12 * noise.noise(p * 4)) * (0.72 if n.z < -0.5 else 1.0))
    body = [(-0.2, 0.22), (0.2, 0.22), (0.24, -0.02), (0.13, -0.26), (-0.13, -0.26), (-0.24, -0.02)]
    Hd.add(t_poly(body, -0.13, 0.12), None, "MetalChitauri", 0.9)
    Hd.add(t_poly([(x * 0.8, y * 0.85) for x, y in body], 0.12, 0.2), None, "RustChitauri", 0.85)
    # yoke underneath to the base
    Hd.add(t_cyl(0.14, 0.09, 10), TR((0, 0, -0.18)), "MetalChitauri", 0.7)
    # side armour fins sweeping back
    for s in (-1, 1):
        fin = [(s * 0.24, -0.05, -0.1), (s * 0.24, -0.2, 0.05), (s * 0.24, 0.1, 0.24), (s * 0.24, 0.32, 0.1),
               (s * 0.24, 0.3, -0.12)]
        Hd.add(t_prism(fin, (s * 0.05, 0, 0)), None, "RustChitauri", 0.75)
        Hd.add(t_box(s * 0.29 - 0.008, -0.12, -0.02, s * 0.29 + 0.008, 0.2, 0.0), None, "GlowCyan")
    # sensor eye
    Hd.add(t_cyl(0.05, 0.03, 10), TR((0.12, -0.24, 0.07), (math.pi / 2, 0, 0)), "GlowRed")
    # barrel along -Y (Godot +Z)
    Hd.add(t_cyl(0.075, 0.25, 10), TR((0, -0.2, 0.0), (math.pi / 2, 0, 0)), "MetalChitauri", 0.8)
    Hd.add(t_cyl(0.055, 0.3, 10), TR((0, -0.42, 0.0), (math.pi / 2, 0, 0)), "MetalChitauri", 0.6)
    for y in (-0.3, -0.42, -0.54):
        Hd.add(t_torus(0.065, 0.016, 10, 4), TR((0, y, 0), (math.pi / 2, 0, 0)), "GlowCyan")
    for k in range(3):
        a = k * 2 * math.pi / 3 + math.pi / 2
        o = Vector((math.cos(a) * 0.07, 0, math.sin(a) * 0.07))
        Hd.add(t_bar(o + Vector((0, -0.6, 0)), o * 1.15 + Vector((0, MUZZLE_Y + 0.01, 0)), 0.018, 0.008, sides=4,
                     smooth=False), None, "RustChitauri", 0.9)
    Hd.add(t_cyl(0.04, 0.03, 10), TR((0, -0.69, 0), (math.pi / 2, 0, 0)), "GlowCyan")
    # antenna fin to 1.1 total height
    Hd.add(t_prism([(0, 0.15, 0.2), (0, -0.05, 0.2), (0, 0.18, HEAD_Z_TOP - HEAD_Z), (0, 0.24, 0.2)], (0.02, 0, 0)),
           TR((-0.01, 0, 0)), "RustChitauri", 0.8)
    head = Hd.finish()
    head.parent = base
    head.location = (0, 0, HEAD_Z)
    mz = bpy.data.objects.new("Muzzle", None)
    bpy.context.collection.objects.link(mz)
    mz.empty_display_size = 0.1
    mz.parent = head
    mz.location = (0, MUZZLE_Y, 0)
    return base, [head, mz]


HEAD_Z_TOP = 1.1


# ================================================================ 5. Power Stone vault (Morag temple)
def vault_walls():
    rng = random.Random(505)

    def g(p, n):
        v = 0.86 + 0.14 * noise.noise(p * 1.1)
        if n.z < -0.5:
            v *= 0.72
        v *= 0.7 + 0.3 * sstep(p.z / 0.8)
        return v

    def moss(p):
        k = (1 - sstep(p.z / 0.7)) * 0.5 + max(0, noise.noise(p * 0.7 + Vector((5, 1, 3)))) * 0.6
        k = clamp(k)
        return (1 - 0.35 * k, 1 - 0.1 * k, 1 - 0.4 * k)
    P = SPiece("VaultWalls", grime=g)
    C = Cols("VaultWalls")
    S = "ConcreteTemple"
    O, I, WH = 6.0, 5.2, 3.0
    course = 0.6

    def wall_run(x0, y0, x1, y1, along_x):
        """Masonry blocks filling a rectangle, in courses."""
        L0, L1 = (x0, x1) if along_x else (y0, y1)
        for c in range(5):
            z0, z1 = c * course, (c + 1) * course
            u = L0
            first = True
            while u < L1 - 1e-4:
                w = rng.uniform(1.0, 1.9)
                if first and c % 2:
                    w *= 0.5
                first = False
                u1 = min(L1, u + w)
                if L1 - u1 < 0.45:
                    u1 = L1
                t = rng.uniform(0.75, 1.0)
                pin = rng.uniform(0.0, 0.03)
                if along_x:
                    P.box(u + 0.012, y0 - pin, z0 + 0.012 if c else 0, u1 - 0.012, y1 + pin, z1 if c == 4 else z1 - 0.012,
                          S, lambda p, t=t: tuple(t * q for q in moss(p)), bevel=0.025)
                else:
                    P.box(x0 - pin, u + 0.012, z0 + 0.012 if c else 0, x1 + pin, u1 - 0.012, z1 if c == 4 else z1 - 0.012,
                          S, lambda p, t=t: tuple(t * q for q in moss(p)), bevel=0.025)
                u = u1
        # mortar core so the joints read dark, not see-through
        P.box(x0 + 0.03, y0 + 0.03, 0, x1 - 0.03, y1 - 0.03, WH - 0.02, "Interior")
    wall_run(-O + 1.4, I, O - 1.4, O, True)               # back
    wall_run(-O, -O + 1.4, -I, O - 1.4, False)            # left
    wall_run(I, -O + 1.4, O, O - 1.4, False)              # right
    wall_run(-O + 1.4, -O, -2.3, -I, True)                 # front left
    wall_run(2.3, -O, O - 1.4, -I, True)                   # front right
    C.box(-O, I, 0, O, O, WH)
    C.box(-O, -O, 0, -I, O, WH)
    C.box(I, -O, 0, O, O, WH)
    C.box(-O, -O, 0, -1.5, -I, WH)
    C.box(1.5, -O, 0, O, -I, WH)
    # corner towers: stepped tops
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (O - 0.75), sy * (O - 0.75)
            P.box(cx - 0.8, cy - 0.8, 0, cx + 0.8, cy + 0.8, 3.1, S, lambda p: tuple(0.9 * q for q in moss(p)), 0.03)
            P.box(cx - 0.88, cy - 0.88, 3.1, cx + 0.88, cy + 0.88, 3.3, S, 0.95, 0.03)
            P.box(cx - 0.6, cy - 0.6, 3.3, cx + 0.6, cy + 0.6, 3.6, S, 0.9, 0.03)
            P.box(cx - 0.35, cy - 0.35, 3.6, cx + 0.35, cy + 0.35, 3.85, S, 0.85, 0.03)
            # carved band on the towers
            for z in (0.9, 2.1):
                P.box(cx - 0.83, cy - 0.83, z, cx + 0.83, cy + 0.83, z + 0.12, S, 0.7, 0.01)
            C.box(cx - 0.88, cy - 0.88, 0, cx + 0.88, cy + 0.88, 3.3)
            C.box(cx - 0.6, cy - 0.6, 3.3, cx + 0.6, cy + 0.6, 3.85)
    # entrance gate: pylons + lintel with the Power Stone glyph
    for s in (-1, 1):
        x0, x1 = sorted((s * 1.5, s * 2.35))
        P.box(x0, -O - 0.3, 0, x1, -I + 0.2, 3.3, S, lambda p: tuple(0.95 * q for q in moss(p)), 0.03)
        for z in (0.0, 1.2, 2.4):
            P.box(x0 - 0.04, -O - 0.34, z, x1 + 0.04, -I + 0.24, z + 0.18, S, 0.75, 0.015)
        # glowing rune column on the pylon face
        xm = (x0 + x1) / 2
        for i in range(5):
            z = 0.5 + i * 0.5
            P.box(xm - 0.12, -O - 0.32, z, xm + 0.12, -O - 0.3, z + 0.05, "GlowViolet")
            P.box(xm - 0.03, -O - 0.32, z + 0.05, xm + 0.03, -O - 0.3, z + 0.22, "GlowViolet")
        C.box(x0, -O - 0.3, 0, x1, -I + 0.2, 3.3)
    P.box(-2.5, -O - 0.4, 3.3, 2.5, -I + 0.25, 3.75, S, 0.92, 0.03)
    P.box(-2.2, -O - 0.3, 3.75, 2.2, -I + 0.15, 4.0, S, 0.85, 0.03)
    P.add(t_cyl(0.32, 0.06, 16), TR((0, -O - 0.4, 3.52), (math.pi / 2, 0, 0)), S, 0.7)
    P.add(t_torus(0.24, 0.035, 16, 4), TR((0, -O - 0.47, 3.52), (math.pi / 2, 0, 0)), "GlowViolet")
    P.add(t_octa(0.1, 0.13), TR((0, -O - 0.47, 3.52), (math.pi / 2, 0, 0)), "GlowViolet")
    C.box(-2.5, -O - 0.4, 3.3, 2.5, -I + 0.25, 4.0)
    # engaged pillars on the inner faces (+ collision)
    pillars = []
    for u in (-2.6, 2.6):
        pillars.append((u, I, 0, -1))           # back, protrude toward -Y
    for u in (-2.6, 0.0, 2.6):
        pillars.append((-I, u, 1, 0))           # left wall, protrude +X
        pillars.append((I, u, -1, 0))           # right wall, protrude -X
    for (px, py, dx, dy) in pillars:
        if dy:
            x0, x1, y0, y1 = px - 0.3, px + 0.3, py - 0.28, py
        else:
            x0, x1 = (px, px + 0.28) if dx > 0 else (px - 0.28, px)
            y0, y1 = py - 0.3, py + 0.3
        P.box(x0, y0, 0, x1, y1, WH - 0.25, S, lambda p: tuple(0.82 * q for q in moss(p)), 0.02)
        P.box(x0 - 0.06, y0 - 0.06, WH - 0.25, x1 + 0.06, y1 + 0.06, WH, S, 0.75, 0.02)
        P.box(x0 - 0.04, y0 - 0.04, 0, x1 + 0.04, y1 + 0.04, 0.22, S, 0.7, 0.02)
        # violet rune slit down the pillar
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if dy:
            P.box(cx - 0.025, y0 - 0.008, 0.6, cx + 0.025, y0, 2.4, "GlowViolet")
        else:
            xf = x1 if dx > 0 else x0
            P.box(min(xf, xf + dx * 0.008), cy - 0.025, 0.6, max(xf, xf + dx * 0.008), cy + 0.025, 2.4, "GlowViolet")
        C.box(x0, y0, 0, x1, y1, WH)
    # carved frieze: glyph blocks along the outer faces
    for k in range(4):
        M = side_M(k)
        u = -O + 1.6
        while u < O - 1.6:
            if k == 0 and -2.5 < u < 2.5:
                u += 0.42
                continue
            kind = rng.randint(0, 3)
            if kind == 0:
                P.box(u, -O - 0.05, 2.15, u + 0.28, -O + 0.01, 2.43, S, 0.65, M=M)
            elif kind == 1:
                P.box(u, -O - 0.05, 2.15, u + 0.28, -O + 0.01, 2.22, S, 0.65, M=M)
                P.box(u + 0.1, -O - 0.05, 2.22, u + 0.18, -O + 0.01, 2.43, S, 0.65, M=M)
            elif kind == 2:
                P.box(u, -O - 0.05, 2.36, u + 0.28, -O + 0.01, 2.43, S, 0.65, M=M)
                P.box(u, -O - 0.05, 2.15, u + 0.08, -O + 0.01, 2.36, S, 0.65, M=M)
                P.box(u + 0.2, -O - 0.05, 2.15, u + 0.28, -O + 0.01, 2.36, S, 0.65, M=M)
            else:
                P.add(t_prism([(u, -O + 0.01, 2.15), (u + 0.28, -O + 0.01, 2.15), (u + 0.14, -O + 0.01, 2.43)],
                              (0, -0.06, 0)), M, S, 0.65)
            u += 0.42
        if k:
            P.box(-O + 1.5, -O - 0.06, 2.05, O - 1.5, -O + 0.01, 2.1, S, 0.6, M=M)
    # inner floor: flagstones (flush-ish, 2 cm)
    n = 8
    st = 2 * I / n
    for i in range(n):
        for j in range(n):
            x0, y0 = -I + i * st, -I + j * st
            P.box(x0 + 0.02, y0 + 0.02, 0.0, x0 + st - 0.02, y0 + st - 0.02, 0.02, S, rng.uniform(0.55, 0.8))
    P.box(-1.5, -O, 0.0, 1.5, -I, 0.02, S, 0.6)
    # dais: 2x2, top exactly 0.4, middle-back
    DY = 2.4
    P.box(-1.0, DY - 1.0, 0, 1.0, DY + 1.0, 0.32, S, 0.8, 0.02)
    P.box(-0.95, DY - 0.95, 0.32, 0.95, DY + 0.95, 0.4, S, 0.95, 0.015)
    for s in (-1, 1):
        y0, y1 = sorted((DY + s * 1.0, DY + s * 1.006))
        P.box(-0.8, y0, 0.14, 0.8, y1, 0.18, "GlowViolet")
        x0, x1 = sorted((s * 1.0, s * 1.006))
        P.box(x0, DY - 0.8, 0.14, x1, DY + 0.8, 0.18, "GlowViolet")
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.add(t_cyl(0.07, 0.06, 8), TR((sx * 0.78, DY + sy * 0.78, 0.4)), S, 0.7)
    C.box(-1.0, DY - 1.0, 0, 1.0, DY + 1.0, 0.4)
    # vines hanging over the wall tops, fallen column drum outside
    for i in range(14):
        k = rng.randint(0, 3)
        u = rng.uniform(-4.3, 4.3)
        if k == 0 and abs(u) < 2.6:
            continue
        side = rng.choice((-1, 1))   # outer or inner face
        y = -O - 0.04 if side < 0 else -I + 0.04
        L = rng.uniform(0.6, 1.8)
        pts = [(u, y + side * 0.0, WH + 0.03), (u + rng.uniform(-0.1, 0.1), y + side * 0.02, WH - L * 0.5),
               (u + rng.uniform(-0.15, 0.15), y + side * 0.03, WH - L)]
        P.add(t_tube([(u, y - side * 0.25, WH + 0.02)] + pts, [0.022] * 4, 4), side_M(k), S,
              (0.35, 0.55, 0.25))
    P.add(t_cyl(0.42, 0.9, 12), TR((-7.0, -3.5, 0.42), (0, math.pi / 2, 0.4)), S, 0.75)
    P.add(t_cyl(0.42, 0.7, 12), TR((6.9, 4.2, 0.0)), S, 0.75)
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ 6. Sanctum Sanctorum
SW = 6.0       # outer half-size
SI = 5.6       # inner half-size
SH = 8.0       # roof/parapet top
CEIL = 7.6     # ceiling (roof slab underside)
LAND_Z = 2.5
BALC_Z = 4.0
STAIR_X0, STAIR_X1 = -5.6, -3.8           # stair width along the left (-X) wall
STAIR_Y0, STAIR_Y1 = -4.4, -0.4            # first step front .. landing front
LAND_Y1 = 1.2                              # broken end of the landing
BALC = (-1.5, 2.5, 3.6, 5.6)               # x0, x1, y0, y1 (back wall)


def sanctum():
    rng = random.Random(606)
    P = SPiece("Sanctum", grime=g_noise(1.0, 0.25, 1.4))
    C = Cols("Sanctum")
    # ---- shell: four walls with window holes (outer brick, inner plaster)
    walls = {
        0: dict(u=(-SW, SW), holes=[(-1.0, 1.0, 0.0, 2.4), (-4.6, -3.0, 0.9, 2.7), (3.0, 4.6, 0.9, 2.7),
                                    (-4.8, -3.4, 3.9, 5.8), (3.4, 4.8, 3.9, 5.8), (-1.6, 1.6, 3.6, 6.4)]),
        1: dict(u=(-SI, SI), holes=[(-4.2, -2.8, 3.9, 6.1), (-0.7, 0.7, 3.9, 6.1), (2.8, 4.2, 3.9, 6.1)]),
        2: dict(u=(-SW, SW), holes=[(-4.8, -3.6, 4.6, 6.6), (3.4, 4.6, 4.6, 6.6)]),
        3: dict(u=(-SI, SI), holes=[(-4.2, -2.8, 3.9, 6.1), (-0.7, 0.7, 3.9, 6.1), (2.8, 4.2, 3.9, 6.1)]),
    }
    lit = {(0, 1), (2, 0), (1, 1)}
    for k, w in walls.items():
        M = side_M(k)
        holes = w["holes"]
        pb = t_panel(w["u"][0], w["u"][1], 0, SH, -SW, -SI, holes, extra_z=(0.7, 3.2, 3.35, 6.75, 6.9, CEIL))
        P.add(pb, M, ["Brick", "PlasterSanctum"], lambda p: 1.0 if p.z > 1.4 else 0.8)
        for hi, (a, b, c, d) in enumerate(holes):
            if k == 0 and hi in (0, 5):
                continue
            # stone sill + lintel, cream frame, sash bars, double glass (dark out, daylight in)
            P.box(a - 0.1, -SW - 0.08, c - 0.1, b + 0.1, -SW + 0.1, c, "TrimStone", 0.9, M=M)
            P.box(a - 0.14, -SW - 0.06, d, b + 0.14, -SW + 0.02, d + 0.22, "TrimStone", 0.95, M=M)
            P.box(a - 0.04, -SW - 0.07, d + 0.22, b + 0.04, -SW - 0.03, d + 0.26, "TrimStone", 0.8, M=M)
            for (u0, u1, z0, z1) in ((a, a + 0.07, c, d), (b - 0.07, b, c, d), (a, b, d - 0.07, d)):
                P.box(u0, -SW + 0.1, z0, u1, -SW + 0.18, z1, "TrimCream", 1.0, M=M)
            gy = -SW + 0.14
            outer = "GlowWindow" if (k, hi) in lit else "Glass"
            P.add(t_quad_facing([(a, gy - 0.005, c), (b, gy - 0.005, c), (b, gy - 0.005, d), (a, gy - 0.005, d)],
                                (0, -1, 0)), M, outer)
            P.add(t_quad_facing([(a, gy + 0.005, c), (b, gy + 0.005, c), (b, gy + 0.005, d), (a, gy + 0.005, d)],
                                (0, 1, 0)), M, "GlassDay")
            um, zm = (a + b) / 2, c + (d - c) * 0.55
            P.box(um - 0.025, gy - 0.03, c, um + 0.025, gy + 0.03, d, "TrimCream", 1.0, M=M)
            P.box(a, gy - 0.03, zm - 0.025, b, gy + 0.03, zm + 0.025, "TrimCream", 1.0, M=M)
            # inner sill
            P.box(a - 0.06, -SI - 0.0, c - 0.05, b + 0.06, -SI + 0.08, c, "Wood", 0.9, M=M)
        # exterior bands: plinth, belt courses, cornice
        u0, u1 = (-SW - 0.06, SW + 0.06)
        if k == 0:
            P.box(u0, -SW - 0.06, 0, -1.0, -SW, 0.7, "TrimStone", 0.8, M=M)
            P.box(1.0, -SW - 0.06, 0, u1, -SW, 0.7, "TrimStone", 0.8, M=M)
        else:
            P.box(u0, -SW - 0.06, 0, u1, -SW, 0.7, "TrimStone", 0.8, M=M)
        for (z0, z1) in ((3.2, 3.35), (6.75, 6.9)):
            if k == 0 and z0 > 6:
                P.box(u0, -SW - 0.05, z0, -1.62, -SW, z1, "TrimStone", 0.9, M=M)
                P.box(1.62, -SW - 0.05, z0, u1, -SW, z1, "TrimStone", 0.9, M=M)
            else:
                P.box(u0, -SW - 0.05, z0, u1, -SW, z1, "TrimStone", 0.9, M=M)
        P.box(-SW - 0.22, -SW - 0.22, 7.55, SW + 0.22, -SW, 7.72, "TrimStone", 0.95, M=M)
        P.box(-SW - 0.3, -SW - 0.3, 7.72, SW + 0.3, -SW, 7.85, "TrimStone", 1.0, M=M)
        P.box(-SW - 0.1, -SW - 0.1, 7.85, SW + 0.1, -SW + 0.3, SH, "TrimStone", 0.85, M=M)
        for i in range(13):
            u = -5.5 + i * (11.0 / 12)
            P.box(u - 0.06, -SW - 0.2, 7.3, u + 0.06, -SW, 7.55, "TrimStone", 0.8, M=M)
        # corner quoins (on the left end of each face)
        for i in range(10):
            z0 = 0.75 + i * 0.68
            if z0 + 0.3 > 7.3:
                break
            wq = 0.55 if i % 2 else 0.35
            P.box(-SW - 0.04, -SW - 0.04, z0, -SW + wq, -SW, z0 + 0.3, "TrimStone", 0.9, M=M)
            P.box(SW - wq, -SW - 0.04, z0, SW + 0.04, -SW, z0 + 0.3, "TrimStone", 0.9, M=M)
    # ---- round window: the Seal of the Vishanti
    WZ, WR = 5.0, 1.35
    P.add(t_sq_ring(0, WZ, 1.6, WR, -SW, -SI), None, ["Brick", "PlasterSanctum", "TrimStone"])
    P.add(t_torus(WR + 0.08, 0.1, 40, 6), TR((0, -SW - 0.02, WZ), (math.pi / 2, 0, 0)), "TrimStone", 0.95)
    P.add(t_torus(WR + 0.08, 0.06, 40, 6), TR((0, -SI + 0.02, WZ), (math.pi / 2, 0, 0)), "Wood", 0.9)
    for a in range(4):   # keystones
        ang = a * math.pi / 2
        c = Vector((math.cos(ang) * (WR + 0.2), -SW - 0.06, WZ + math.sin(ang) * (WR + 0.2)))
        P.add(t_box(-0.13, -0.05, -0.1, 0.13, 0.05, 0.1), TR(c, (0, -ang, 0)), "TrimStone", 1.0)
    GY = -5.8
    P.add(t_disc(WR, 32, GY - 0.004, -1), TR((0, 0, WZ)), "GlowSeal")
    P.add(t_disc(WR, 32, GY + 0.004, 1), TR((0, 0, WZ)), "GlowSeal")
    lead = []
    lead.append(arc_pts((0, WZ), WR - 0.02, 0, 2 * math.pi, 40, GY))
    lead.append(arc_pts((0, WZ), 0.42, 0, 2 * math.pi, 20, GY))
    for k in range(3):
        a = math.pi / 2 + k * 2 * math.pi / 3
        cx, cz = 0.62 * math.cos(a), WZ + 0.62 * math.sin(a)
        pts = arc_pts((cx, cz), 0.98, a + math.pi * 0.42, a + math.pi * 1.58, 20, GY)
        pts = [p for p in pts if math.hypot(p.x, p.z - WZ) <= WR - 0.03]
        if len(pts) > 1:
            lead.append(pts)
    for k in range(4):   # four sweeping diagonal swirls through the centre ring
        a = math.pi / 4 + k * math.pi / 2
        pts = [Vector((math.cos(a + t * 0.9) * r, GY, WZ + math.sin(a + t * 0.9) * r))
               for t, r in ((0, 0.42), (0.35, 0.75), (0.7, 1.05), (1.0, WR - 0.03))]
        lead.append(pts)
    for pts in lead:
        P.add(t_tube(pts, [0.035] * len(pts), 4, caps=False), None, "Wood", 0.5)
    # ---- door: surround, threshold, open leaves
    for s in (-1, 1):
        x0, x1 = sorted((s * 1.0, s * 1.32))
        P.box(x0, -SW - 0.14, 0, x1, -SW + 0.01, 2.55, "TrimStone", 0.95, bevel=0.02)
        P.box(x0 - 0.04, -SW - 0.17, 0, x1 + 0.04, -SW + 0.01, 0.3, "TrimStone", 0.8)
    P.box(-1.5, -SW - 0.2, 2.55, 1.5, -SW + 0.01, 2.85, "TrimStone", 1.0, bevel=0.02)
    P.add(t_prism([(-1.6, -SW - 0.24, 2.85), (1.6, -SW - 0.24, 2.85), (0, -SW - 0.24, 3.15)], (0, 0.25, 0)), None,
          "TrimStone", 0.95)
    P.box(-1.0, -SW - 0.002, 2.4, 1.0, -SI, 2.55, "Wood", 0.8)
    P.box(-1.4, -SW - 0.7, 0, 1.4, -SW, 0.03, "TrimStone", 0.75)
    for s in (-1, 1):
        ang = s * math.radians(-72)
        hinge = TR((s * 1.0, -SI, 0), (0, 0, ang))
        leaf = t_box(-0.96 if s > 0 else 0, -0.06, 0, 0 if s > 0 else 0.96, 0.0, 2.36)
        P.add(leaf, hinge, "Wood", 0.75)
        for (z0, z1) in ((0.2, 1.05), (1.25, 2.15)):
            P.add(t_box(-0.82 if s > 0 else 0.14, -0.08, z0, -0.14 if s > 0 else 0.82, -0.06, z1), hinge, "Wood", 1.05)
        P.add(t_cyl(0.03, 0.04, 6), hinge @ TR((-0.85 if s > 0 else 0.85, -0.1, 1.15), (math.pi / 2, 0, 0)), "Gold")
    # ---- roof
    P.box(-SI, -SI, CEIL, SI, SI, CEIL + 0.2, "PlasterCeiling", 1.0)
    P.box(-SW + 0.1, -SW + 0.1, CEIL + 0.2, SW - 0.1, SW - 0.1, CEIL + 0.22, "ConcreteDark", 0.8)
    for sx in (-1, 1):
        P.box(sx * 4.2 - 0.45, 4.2, CEIL, sx * 4.2 + 0.45, 5.1, CEIL + 1.4, "Brick", 0.85)
        P.box(sx * 4.2 - 0.52, 4.13, CEIL + 1.4, sx * 4.2 + 0.52, 5.17, CEIL + 1.52, "TrimStone", 0.85)
        for dx in (-0.2, 0.2):
            P.add(t_cyl(0.1, 0.2, 8), TR((sx * 4.2 + dx, 4.65, CEIL + 1.52)), "ConcreteDark", 0.5)
    # skylight lantern
    P.box(-1.4, -1.4, CEIL + 0.2, 1.4, 1.4, CEIL + 0.5, "TrimStone", 0.9)
    P.add(t_cyl(1.25, 0.7, 4, r2=0.15, smooth=False), TR((0, 0, CEIL + 0.5), (0, 0, math.pi / 4)), "Glass")
    for a in range(4):
        ang = a * math.pi / 2 + math.pi / 4
        P.add(t_bar((1.25 * math.cos(ang), 1.25 * math.sin(ang), CEIL + 0.5),
                    (0.15 * math.cos(ang), 0.15 * math.sin(ang), CEIL + 1.2), 0.03, sides=4), None, "Wood", 0.6)
    # ---- interior: floor planks
    n = 32
    w = 2 * SI / n
    for i in range(n):
        x0 = -SI + i * w
        P.box(x0 + 0.004, -SI, -0.06, x0 + w - 0.004, SI, 0.0, "WoodFloor", rng.uniform(0.7, 1.08))
    P.box(-SI, -SI, -0.08, SI, SI, -0.055, "Interior")
    # wainscot panelling + crown moulding on every inner wall
    for k in range(4):
        M = side_M(k)
        y = -SI
        segs = [(-SI, SI)] if k else [(-SI, -1.0), (1.0, SI)]
        for (a, b) in segs:
            P.box(a, y, 0, b, y + 0.04, 1.4, "Wood", 0.75, M=M)
            P.box(a, y, 0, b, y + 0.08, 0.18, "Wood", 0.6, M=M)
            P.box(a, y, 1.3, b, y + 0.09, 1.42, "Wood", 0.95, M=M)
            u = a + 0.05
            while u < b - 0.3:
                P.box(u, y, 0.18, u + 0.08, y + 0.07, 1.3, "Wood", 0.9, M=M)
                u += 0.9
            P.box(a, y, CEIL - 0.25, b, y + 0.12, CEIL, "Wood", 0.85, M=M)
            P.box(a, y, CEIL - 0.34, b, y + 0.06, CEIL - 0.25, "Gold", 0.8, M=M)
    # ceiling beams
    for i in range(5):
        x = -4.4 + i * 2.2
        P.box(x - 0.14, -SI, CEIL - 0.3, x + 0.14, SI, CEIL, "Wood", 0.8)
    # ---- grand staircase along the left wall (rises toward the back), landing at 2.5
    nst = 10
    rise = LAND_Z / nst
    tread = (STAIR_Y1 - STAIR_Y0) / nst
    for i in range(nst):
        y0 = STAIR_Y0 + i * tread
        top = (i + 1) * rise
        P.box(STAIR_X0, y0, 0, STAIR_X1, y0 + tread, top - 0.04, "PlasterCeiling", 0.85)
        P.box(STAIR_X0, y0 - 0.03, top - 0.04, STAIR_X1 + 0.02, y0 + tread, top, "Wood", 0.95)
        P.box(-5.25, y0 - 0.032, top - 0.005, -4.15, y0 + tread, top + 0.006, "Rug", 0.95)
        P.box(-5.25, y0 - 0.035, top - rise, -4.15, y0 - 0.03, top, "Rug", 0.8)
    # closed stringer on the open side
    k = LAND_Z / (STAIR_Y1 - STAIR_Y0 + tread)       # slope through the nosings
    yb = STAIR_Y0 - tread

    def zline(y):
        return k * (y - yb) + 0.12
    sp = [(STAIR_X1 - 0.02, STAIR_Y0 - 0.05, 0), (STAIR_X1 - 0.02, STAIR_Y1, 0),
          (STAIR_X1 - 0.02, STAIR_Y1, zline(STAIR_Y1)), (STAIR_X1 - 0.02, STAIR_Y0 - 0.05, zline(STAIR_Y0 - 0.05))]
    P.add(t_prism(sp, (0.1, 0, 0)), None, "Wood", 0.8)
    # balusters + handrail + newel
    yy = STAIR_Y0 + 0.1
    while yy < STAIR_Y1 - 0.05:
        P.add(t_cyl(0.025, 0.85, 6), TR((STAIR_X1 + 0.03, yy, zline(yy))), "Wood", 1.1)
        yy += tread / 1.5
    P.add(t_bar((STAIR_X1 + 0.03, STAIR_Y0 - 0.05, zline(STAIR_Y0) + 0.86),
                (STAIR_X1 + 0.03, STAIR_Y1 + 0.05, zline(STAIR_Y1) + 0.86), 0.045, sides=6), None, "Wood", 0.9)
    P.box(STAIR_X1 - 0.06, STAIR_Y0 - 0.22, 0, STAIR_X1 + 0.14, STAIR_Y0 - 0.02, 1.25, "Wood", 0.85, bevel=0.015)
    P.add(t_cyl(0.09, 0.12, 10), TR((STAIR_X1 + 0.04, STAIR_Y0 - 0.12, 1.25)), "Gold")
    P.box(STAIR_X1 - 0.06, STAIR_Y1 - 0.1, LAND_Z, STAIR_X1 + 0.14, STAIR_Y1 + 0.1, LAND_Z + 1.0, "Wood", 0.85)
    # landing slab with a broken back end
    lw = STAIR_X1 - STAIR_X0
    ld = LAND_Y1 - STAIR_Y1
    slab, lpts = jagged_slab(rng, -lw / 2, lw / 2, -ld / 2 - 0.12, ld / 2, 0.3, "y0", n=6, amp=0.26)
    LM = TR(((STAIR_X0 + STAIR_X1) / 2, (STAIR_Y1 + LAND_Y1) / 2, LAND_Z - 0.3), (0, 0, math.pi))
    P.add(slab, LM, "Wood", 0.85)
    P.box(STAIR_X0, STAIR_Y1, LAND_Z - 0.006, STAIR_X1 - 0.1, LAND_Y1 - 0.25, LAND_Z + 0.004, "Rug", 0.9)
    for (x, y) in lpts[2:-1]:
        p = LM @ Vector((x, y, 0.15))
        if rng.random() < 0.6:
            P.add(t_bar(p, p + Vector((rng.uniform(-0.1, 0.1), rng.uniform(0.05, 0.25), -rng.uniform(0.1, 0.4))),
                        0.02, 0.008, sides=3, smooth=False), None, "Wood", 0.6)
    P.box(STAIR_X1 - 0.12, LAND_Y1 - 0.3, 0, STAIR_X1 + 0.08, LAND_Y1 - 0.1, LAND_Z - 0.3, "TrimStone", 0.85,
          bevel=0.02)
    P.box(STAIR_X1 - 0.18, LAND_Y1 - 0.36, 0, STAIR_X1 + 0.14, LAND_Y1 - 0.04, 0.25, "TrimStone", 0.75)
    # the missing flight: torn stringer stub on the wall, bare wall scar, rubble below
    P.add(t_prism([(STAIR_X0 + 0.002, LAND_Y1 - 0.2, LAND_Z - 0.3), (STAIR_X0 + 0.002, LAND_Y1 + 0.75, LAND_Z + 0.25),
                   (STAIR_X0 + 0.002, LAND_Y1 + 0.55, LAND_Z + 0.45), (STAIR_X0 + 0.002, LAND_Y1 - 0.2, LAND_Z + 0.05)],
                  (0.12, 0, 0)), None, "Wood", 0.65)
    P.add(t_quad_facing([(STAIR_X0 + 0.003, LAND_Y1 + 0.6, LAND_Z + 0.4), (STAIR_X0 + 0.003, 4.6, 5.0),
                         (STAIR_X0 + 0.003, 4.6, 5.35), (STAIR_X0 + 0.003, LAND_Y1 + 0.6, LAND_Z + 0.75)], (1, 0, 0)),
          None, "Interior")
    for i in range(14):
        s = rng.uniform(0.1, 0.32)
        x, y = rng.uniform(-5.3, -4.0), rng.uniform(LAND_Y1 + 0.4, 3.4)
        if rng.random() < 0.5:
            P.add(t_box(-s * 1.8, -s * 0.5, 0, s * 1.8, s * 0.5, 0.06), TR((x, y, 0.0), (rng.uniform(-0.3, 0.3), 0.15,
                                                                                    rng.uniform(0, 3))), "Wood", 0.7)
        else:
            P.add(t_rock(rng, s, s * 0.8, s * 0.6), TR((x, y, 0)), "PlasterCeiling", rng.uniform(0.6, 0.85))
    for i in range(3):
        P.add(t_cyl(0.025, 0.8, 6), TR((rng.uniform(-5.2, -4.1), rng.uniform(1.8, 3.2), 0.05),
                                       (math.pi / 2, 0, rng.uniform(0, 3))), "Wood", 1.1)
    # stair collision: wedge ramp (32 deg) through the nosings, landing slab + its column
    C.hull([(x, y, z) for x in (STAIR_X0, STAIR_X1) for (y, z) in
            ((yb, 0.0), (STAIR_Y1, 0.0), (STAIR_Y1, LAND_Z))])
    C.box(STAIR_X0, STAIR_Y1, LAND_Z - 0.3, STAIR_X1, LAND_Y1, LAND_Z)
    C.box(STAIR_X1 - 0.18, LAND_Y1 - 0.36, 0, STAIR_X1 + 0.14, LAND_Y1 - 0.04, LAND_Z - 0.3)
    C.hull([(STAIR_X1 - 0.02, y, z) for (y, z) in ((STAIR_Y0 - 0.05, 0), (STAIR_Y1, 0))] +
           [(STAIR_X1 + 0.08, y, z) for (y, z) in ((STAIR_Y0 - 0.05, 0), (STAIR_Y1, 0))] +
           [(x, y, zline(y) + 0.9) for x in (STAIR_X1 - 0.02, STAIR_X1 + 0.08) for y in (STAIR_Y0 - 0.05, STAIR_Y1)])
    # ---- balcony on the back wall: top exactly 4.0, 2 m deep, 4 m wide
    bx0, bx1, by0, by1 = BALC
    P.box(bx0, by0, BALC_Z - 0.3, bx1, by1, BALC_Z, "Wood", 0.8)
    P.box(bx0 - 0.05, by0 - 0.06, BALC_Z - 0.32, bx1 + 0.05, by0 + 0.05, BALC_Z - 0.12, "TrimStone", 0.95)
    P.box(bx0 - 0.07, by0 - 0.08, BALC_Z - 0.12, bx1 + 0.07, by0 + 0.05, BALC_Z - 0.05, "Gold", 0.8)
    P.box(bx0 + 0.25, by0 + 0.25, BALC_Z - 0.004, bx1 - 0.35, by1 - 0.15, BALC_Z + 0.006, "RugBlue", 1.0)
    P.box(bx0 + 0.4, by0 + 0.4, BALC_Z, bx1 - 0.5, by1 - 0.3, BALC_Z + 0.01, "RugGold", 1.0)
    for x in (bx0 + 0.4, (bx0 + bx1) / 2, bx1 - 0.4):
        P.add(t_prism([(x - 0.1, by1, BALC_Z - 0.3), (x - 0.1, by0 + 0.1, BALC_Z - 0.3),
                       (x - 0.1, by1 - 0.2, BALC_Z - 1.3), (x - 0.1, by1, BALC_Z - 1.4)], (0.2, 0, 0)), None,
              "TrimStone", 0.9)
    # low balustrade (0.45) on the front edge with a broken gap, and on the right side
    rail_segs = [((bx0, by0, bx0 + 1.4, by0 + 0.1), "x"), ((bx0 + 2.8, by0, bx1, by0 + 0.1), "x"),
                 ((bx1 - 0.1, by0, bx1, by1), "y")]
    for (x0, y0, x1, y1), ax in rail_segs:
        P.box(x0, y0, BALC_Z, x1, y1, BALC_Z + 0.06, "Wood", 0.8)
        P.box(x0 - 0.02, y0 - 0.02, BALC_Z + 0.4, x1 + 0.02, y1 + 0.02, BALC_Z + 0.46, "Wood", 0.9)
        L = (x1 - x0) if ax == "x" else (y1 - y0)
        nb = int(L / 0.2)
        for i in range(nb + 1):
            t = i / nb
            x = x0 + 0.05 + (x1 - x0 - 0.1) * t if ax == "x" else (x0 + x1) / 2
            y = (y0 + y1) / 2 if ax == "x" else y0 + 0.05 + (y1 - y0 - 0.1) * t
            P.add(t_cyl(0.025, 0.34, 6), TR((x, y, BALC_Z + 0.06)), "TrimStone", 1.0)
        C.box(x0, y0, BALC_Z, x1, y1, BALC_Z + 0.46)
    # broken-off rail end hanging + a fallen baluster in the gap
    P.add(t_bar((bx0 + 1.4, by0 + 0.05, BALC_Z + 0.43), (bx0 + 1.75, by0 - 0.1, BALC_Z + 0.05), 0.03, sides=5), None,
          "Wood", 0.9)
    P.add(t_cyl(0.025, 0.34, 6), TR((bx0 + 2.1, by0 + 0.3, BALC_Z + 0.03), (math.pi / 2, 0, 0.6)), "TrimStone", 0.9)
    C.box(bx0, by0, BALC_Z - 0.3, bx1, by1, BALC_Z)
    # Eye of Agamotto mandala on the back wall above the balcony (Time Stone green)
    MX, MZ = (bx0 + bx1) / 2, 5.75
    P.add(t_cyl(1.05, 0.04, 32), TR((MX, SI - 0.0, MZ), (math.pi / 2, 0, 0)), "Wood", 0.6)
    P.add(t_torus(0.95, 0.04, 32, 4), TR((MX, SI - 0.06, MZ), (math.pi / 2, 0, 0)), "GlowGreen")
    P.add(t_torus(0.7, 0.025, 28, 4), TR((MX, SI - 0.06, MZ), (math.pi / 2, 0, 0)), "Gold")
    for i in range(8):
        a = i * math.pi / 4
        P.add(t_bar((MX + 0.72 * math.cos(a), SI - 0.06, MZ + 0.72 * math.sin(a)),
                    (MX + 0.92 * math.cos(a), SI - 0.06, MZ + 0.92 * math.sin(a)), 0.02, sides=4), None, "Gold")
    eye = [Vector((MX + 0.55 * math.cos(t), SI - 0.07, MZ + 0.26 * math.sin(t))) for t in
           [i * 2 * math.pi / 20 for i in range(21)]]
    P.add(t_tube(eye, [0.025] * len(eye), 4, caps=False), None, "Gold")
    P.add(t_cyl(0.16, 0.03, 16), TR((MX, SI - 0.04, MZ), (math.pi / 2, 0, 0)), "GlowGreen")
    # relic stands at the balcony back corners (stone spot stays clear)
    for x in (bx0 + 0.35, bx1 - 0.45):
        P.add(t_cyl(0.16, 0.7, 8), TR((x, by1 - 0.3, BALC_Z)), "TrimStone", 0.9)
        P.add(t_cyl(0.2, 0.06, 8), TR((x, by1 - 0.3, BALC_Z + 0.7)), "Gold")
        P.add(t_octa(0.09, 0.12), TR((x, by1 - 0.3, BALC_Z + 0.9)), "GlowAmber")
    # ---- bookshelves
    def bookcase(M, a, b, h=2.4, d=0.5):
        y0 = -SI
        P.box(a, y0, 0, b, y0 + d, 0.12, "Wood", 0.7, M=M)
        P.box(a, y0, h - 0.1, b, y0 + d + 0.05, h, "Wood", 0.85, M=M)
        P.box(a, y0, 0, a + 0.06, y0 + d, h, "Wood", 0.85, M=M)
        P.box(b - 0.06, y0, 0, b, y0 + d, h, "Wood", 0.85, M=M)
        P.box(a, y0, 0, b, y0 + 0.03, h, "Wood", 0.5, M=M)
        nsh = 5
        sh = (h - 0.22) / nsh
        for s in range(nsh):
            z = 0.12 + s * sh
            if s:
                P.box(a, y0, z - 0.03, b, y0 + d, z, "Wood", 0.8, M=M)
            u = a + 0.08
            while u < b - 0.14:
                bw = rng.uniform(0.05, 0.11)
                bh = sh * rng.uniform(0.6, 0.88)
                col = rng.choice([(0.45, 0.08, 0.06), (0.1, 0.2, 0.12), (0.12, 0.12, 0.28), (0.4, 0.28, 0.12),
                                  (0.25, 0.1, 0.18), (0.55, 0.45, 0.3), (0.08, 0.08, 0.08)])
                col = tuple(c * rng.uniform(0.8, 1.2) for c in col)
                if rng.random() < 0.06 and u < b - 0.4:
                    P.add(t_box(0, 0.06, 0, bw, d - 0.06, bh), M @ TR((u + bh * 0.4, 0, z), (0, -0.45, 0)) @
                          TR((0, y0, 0)), "Book", col)
                    u += bh * 0.6 + 0.05
                    continue
                P.box(u, y0 + 0.06 + rng.uniform(0, 0.04), z, u + bw - 0.006, y0 + d - 0.04, z + bh, "Book", col, M=M)
                u += bw
            if rng.random() < 0.3:
                u = rng.uniform(a + 0.2, b - 0.3)
                P.add(t_cyl(0.06, 0.04, 8), M @ TR((u, y0 + d * 0.5, z + sh * 0.65)), "Gold")
        C.box(a, y0, 0, b, y0 + d + 0.05, h, M=M)
    bookcase(side_M(1), -4.7, -2.9)
    bookcase(side_M(1), -2.75, -1.25)
    bookcase(side_M(1), 1.25, 2.75)
    bookcase(side_M(1), 2.9, 4.7)
    bookcase(side_M(2), 3.4, 5.4)          # back wall, left end (x -5.4..-3.4)
    bookcase(side_M(2), -5.4, -3.0)        # back wall, right end
    bookcase(side_M(2), -2.3, 1.3, h=2.2)   # under the balcony
    bookcase(side_M(3), -5.4, -3.8)         # left wall, back corner (y 3.8..5.4)
    # ---- fireplace (right wall, centre) with a painting over it
    FM = side_M(1)
    fp = t_panel(-1.1, 1.1, 0, 1.55, -SI + 0.3, -SI, [(-0.6, 0.6, 0.0, 0.95)])
    P.add(fp, FM @ TR((0, 0, 0)) @ Matrix.Scale(1, 4), ["TrimStone", "TrimStone"], 0.95)
    P.box(-1.2, -SI, 1.55, 1.2, -SI + 0.42, 1.68, "TrimStone", 1.0, M=FM)
    P.box(-0.6, -SI, 0, 0.6, -SI + 0.3, 0.02, "Interior", M=FM)
    P.box(-0.6, -SI + 0.0, 0.02, 0.6, -SI + 0.02, 0.95, "Interior", M=FM)
    for i in range(5):
        P.add(t_rock(rng, 0.12, 0.08, 0.06), FM @ TR((rng.uniform(-0.4, 0.4), -SI + 0.15, 0.04)), "GlowEmber")
    P.add(t_bar((-0.35, -SI + 0.15, 0.1), (0.35, -SI + 0.18, 0.12), 0.05, sides=5), FM, "Wood", 0.4)
    C.box(-1.2, -SI, 0, 1.2, -SI + 0.42, 1.68, M=FM)
    P.box(-0.95, -SI, 2.2, 0.95, -SI + 0.06, 3.5, "Gold", 0.9, M=FM)
    P.box(-0.85, -SI, 2.3, 0.85, -SI + 0.07, 3.4, "RugBlue", 0.9, M=FM)
    P.add(t_cyl(0.32, 0.01, 16), FM @ TR((0, -SI + 0.08, 2.85), (math.pi / 2, 0, 0)), "GlowAmber")
    # ---- tapestries/banners on the left wall over the stairs, by the door
    for (u, z) in ((-1.0, 4.4), (-4.0, 3.2)):
        M = side_M(3)
        P.box(u - 0.6, -SI, z, u + 0.6, -SI + 0.03, z + 2.0, "Rug", 0.9, M=M)
        P.box(u - 0.5, -SI, z + 0.1, u + 0.5, -SI + 0.035, z + 1.9, "RugGold", 0.8, M=M)
        P.box(u - 0.4, -SI, z + 0.2, u + 0.4, -SI + 0.04, z + 1.8, "Rug", 0.75, M=M)
        P.add(t_bar((u - 0.75, -SI + 0.06, z + 2.05), (u + 0.75, -SI + 0.06, z + 2.05), 0.03, sides=6), M, "Gold")
    # ---- rugs
    def rug(x0, y0, x1, y1, z=0.0):
        P.box(x0, y0, z, x1, y1, z + 0.012, "RugGold", 1.0)
        P.box(x0 + 0.18, y0 + 0.18, z + 0.012, x1 - 0.18, y1 - 0.18, z + 0.016, "Rug", 1.0)
        P.box(x0 + 0.32, y0 + 0.32, z + 0.016, x1 - 0.32, y1 - 0.32, z + 0.018, "RugBlue", 0.7)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = min(x1 - x0, y1 - y0) * 0.28
        P.add(t_cyl(r, 0.006, 24), TR((cx, cy, z + 0.018)), "RugGold")
        P.add(t_cyl(r * 0.65, 0.006, 24), TR((cx, cy, z + 0.02)), "Rug")
    rug(-2.6, -3.4, 2.6, 2.2)
    P.box(-0.7, -SI, 0, 0.7, -3.4, 0.012, "Rug", 0.9)
    rug(2.4, -1.4, 4.9, 1.4)
    # ---- relic cases + the Cloak of Levitation
    def case(x, y, w=0.62, h=1.42, cloak=False):
        hw = w / 2
        P.box(x - hw, y - hw, 0, x + hw, y + hw, 0.75 if not cloak else 0.2, "Wood", 0.8, bevel=0.015)
        top = h
        z0 = 0.75 if not cloak else 0.2
        P.box(x - hw - 0.02, y - hw - 0.02, top, x + hw + 0.02, y + hw + 0.02, top + 0.08, "Wood", 0.85)
        for sx in (-1, 1):
            for sy in (-1, 1):
                P.box(x + sx * hw - 0.025, y + sy * hw - 0.025, z0, x + sx * hw + 0.025, y + sy * hw + 0.025, top,
                      "Gold", 0.9)
        P.box(x - hw + 0.02, y - hw + 0.02, z0, x + hw - 0.02, y + hw - 0.02, top, "GlassCase")
        if cloak:
            P.add(t_cyl(0.06, 1.6, 8), TR((x, y, 0.2)), "Wood", 0.5)
            P.add(t_cyl(0.26, 1.2, 8, r2=0.14, smooth=True), TR((x, y, 0.4)), "Cloak", 1.0)
            P.add(t_cyl(0.18, 0.22, 8, r2=0.2), TR((x, y, 1.6)), "Cloak", 0.8)
            P.add(t_cyl(0.05, 0.04, 8), TR((x, y - 0.17, 1.58), (math.pi / 2, 0, 0)), "Gold")
        else:
            P.add(t_cyl(0.12, 0.06, 10), TR((x, y, 0.75)), "Gold")
            g = rng.choice(["GlowAmber", "GlowCyan", "GlowViolet", "GlowGreen"])
            P.add(t_octa(0.08, 0.12) if rng.random() < 0.5 else t_torus(0.1, 0.025, 12, 4),
                  TR((x, y, 0.98), (rng.uniform(0, 1), 0, 0)), g)
        C.box(x - hw - 0.02, y - hw - 0.02, 0, x + hw + 0.02, y + hw + 0.02, top + 0.08)
    case(3.6, -3.6)
    case(3.6, 3.0)
    case(-2.5, 3.4)
    case(-2.4, -4.7, w=0.75, h=2.0, cloak=True)
    # ---- chandelier
    CX, CY, CZ = 0.0, -0.6, 5.6
    P.add(t_cyl(0.025, CEIL - CZ - 0.3, 6), TR((CX, CY, CZ + 0.3)), "Gold", 0.7)
    P.add(t_cyl(0.2, 0.08, 10), TR((CX, CY, CEIL - 0.08)), "Gold", 0.8)
    P.add(t_cyl(0.09, 0.5, 8, r2=0.05), TR((CX, CY, CZ - 0.25)), "Gold")
    P.add(t_octa(0.1, 0.16), TR((CX, CY, CZ - 0.32)), "Gold")
    for R, z, nc in ((1.05, CZ, 12), (0.6, CZ + 0.32, 8)):
        P.add(t_torus(R, 0.035, 24, 5), TR((CX, CY, z)), "Gold")
        for i in range(4):
            a = i * math.pi / 2 + 0.3
            P.add(t_bar((CX, CY, z + 0.2), (CX + R * math.cos(a), CY + R * math.sin(a), z), 0.018, sides=4), None,
                  "Gold", 0.8)
        for i in range(nc):
            a = 2 * math.pi * i / nc
            px, py = CX + R * math.cos(a), CY + R * math.sin(a)
            P.add(t_cyl(0.045, 0.03, 6), TR((px, py, z + 0.02)), "Gold")
            P.add(t_cyl(0.028, 0.16, 6), TR((px, py, z + 0.05)), "Candle")
            P.add(t_octa(0.022, 0.045), TR((px, py, z + 0.25)), "GlowAmber")
    # ---- outer shell collision (door gap only), floor, roof
    C.box(-SW, SI, 0, SW, SW, SH)                 # back
    C.box(-SW, -SW, 0, -SI, SW, SH)               # left
    C.box(SI, -SW, 0, SW, SW, SH)                 # right
    C.box(-SW, -SW, 0, -1.0, -SI, SH)             # front, left of door
    C.box(1.0, -SW, 0, SW, -SI, SH)               # front, right of door
    C.box(-1.0, -SW, 2.4, 1.0, -SI, SH)           # over the door
    C.box(-SW, -SW, CEIL, SW, SW, CEIL + 0.22)    # roof
    C.box(-SW, -SW, -0.3, SW, SW, 0.0)            # floor
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ 7. Vormir spire
SPIRE_TOP = 7.0


def vormir_spire():
    rng = random.Random(707)

    def g(p, n):
        v = 0.8 + 0.2 * noise.noise(p * Vector((1.2, 1.2, 3.5)))
        band = 0.5 + 0.5 * math.sin(p.z * 5.0 + 2 * noise.noise(p * 0.8))
        v *= 0.85 + 0.15 * band
        if n.z < -0.5:
            v *= 0.65
        if n.z > 0.8:
            v *= 1.15
        return v
    P = SPiece("VormirSpire", grime=g)
    C = Cols("VormirSpire")
    seg = 14
    off = Vector((11.3, 2.7, 5.1))
    prof = [(0.0, 1.75, 0.28), (0.4, 1.62, 0.25), (1.2, 1.5, 0.22), (2.0, 1.42, 0.2), (2.8, 1.38, 0.18),
            (3.6, 1.36, 0.18), (4.4, 1.38, 0.18), (5.2, 1.42, 0.17), (6.0, 1.5, 0.14), (6.6, 1.6, 0.1),
            (6.88, 1.62, 0.05), (SPIRE_TOP, 1.58, 0.0)]
    rings = []
    for z, r, amp in prof:
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            d = Vector((math.cos(a), math.sin(a), 0))
            rr = r + amp * (noise.noise(d * 1.6 + off + Vector((0, 0, z * 0.9))) * 1.3 +
                            0.4 * noise.noise(d * 4 + off + Vector((0, 0, z * 2.5))))
            if z >= SPIRE_TOP - 0.15:
                # keep a full 2x2 flat top inside the rim
                rr = max(rr, 1.5 / max(abs(d.x), abs(d.y), 0.72) * 0.98, 1.48)
            ring.append(Vector((d.x * rr, d.y * rr, z)))
        rings.append(ring)
    P.add(t_loft(rings, True, True), None, "ConcreteVormir")
    # vertical cracks / fins for a sheer, faceted cliff look
    for i in range(9):
        a = rng.uniform(0, 2 * math.pi)
        d = Vector((math.cos(a), math.sin(a), 0))
        z0 = rng.uniform(0.0, 3.5)
        z1 = min(SPIRE_TOP - 0.4, z0 + rng.uniform(1.5, 3.0))
        r = 1.36
        P.add(t_prism([(d.x * (r - 0.1) - d.y * 0.18, d.y * (r - 0.1) + d.x * 0.18, z0),
                       (d.x * (r + 0.12), d.y * (r + 0.12), z0 + 0.3),
                       (d.x * (r - 0.1) + d.y * 0.18, d.y * (r - 0.1) - d.x * 0.18, z0)], (0, 0, z1 - z0)),
              None, "ConcreteVormir", 0.75)
    # ledges: flat tops at 2.5 (-X) and 4.5 (+X), ~1 m out from the cliff face
    def ledge(sx, h):
        x_in, x_out = sx * 1.1, sx * 2.45
        top = [(x_in, -0.7), (x_out, -0.55), (sx * 2.55, 0.0), (x_out, 0.6), (x_in, 0.72)]
        if sx < 0:
            top = top[::-1]
        bot = [(x * 0.8 if abs(x) > 1.5 else x, y * 0.6) for x, y in top]
        rings_l = [[Vector((x, y, h - 0.75)) for x, y in [(sx * 1.2, yy * 0.4) for _, yy in top]],
                   [Vector((x, y, h - 0.3)) for x, y in bot],
                   [Vector((x, y, h)) for x, y in top]]
        P.add(t_loft(rings_l, True, True), None, "ConcreteVormir", 0.9)
        for i in range(3):
            s = rng.uniform(0.07, 0.13)
            P.add(t_rock(rng, s * 1.3, s, s * 0.7), TR((sx * rng.uniform(2.0, 2.3), rng.uniform(-0.4, 0.4), h)),
                  "ConcreteVormir", 0.7)
        x0, x1 = sorted((sx * 1.2, sx * 2.45))
        C.box(x0, -0.6, h - 0.3, x1, 0.6, h)
    ledge(-1, 2.5)
    ledge(1, 4.5)
    # summit: a few loose stones at the rim, the middle stays clear
    for i in range(8):
        a = rng.uniform(0, 2 * math.pi)
        s = rng.uniform(0.06, 0.14)
        P.add(t_rock(rng, s * 1.3, s, s * 0.7), TR((1.3 * math.cos(a), 1.3 * math.sin(a), SPIRE_TOP)),
              "ConcreteVormir", 0.75)
    # boulders at the foot
    for i in range(9):
        a = rng.uniform(0, 2 * math.pi)
        s = rng.uniform(0.2, 0.5)
        P.add(t_rock(rng, s * 1.3, s, s * 0.8, sub=1), TR((2.0 * math.cos(a), 2.0 * math.sin(a), 0.0),
                                                          (0, 0, rng.uniform(0, 6))), "ConcreteVormir", 0.7)
    # collision: three stacked convex frustums following the rock, sheer sides
    def frustum(z0, z1, r0, r1, n=10):
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            pts.append((r0 * math.cos(a), r0 * math.sin(a), z0))
            pts.append((r1 * math.cos(a), r1 * math.sin(a), z1))
        return C.hull(pts)
    frustum(0.0, 2.5, 1.7, 1.42)
    frustum(2.5, 4.5, 1.42, 1.4)
    frustum(4.5, SPIRE_TOP, 1.4, 1.58)
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ 8. Force-field pylon
def force_pylon():
    P = SPiece("ForceFieldPylon", grime=ck.grime_prop(0.25))
    C = Cols("ForceFieldPylon")
    P.add(t_cyl(0.32, 0.1, 6, smooth=False), None, "MetalChitauri", 0.8)
    P.add(t_cyl(0.24, 0.1, 6, r2=0.2, smooth=False), TR((0, 0, 0.1)), "RustChitauri", 0.8)
    P.add(t_torus(0.26, 0.02, 12, 4), TR((0, 0, 0.1)), "GlowCyan")
    P.add(t_cyl(0.11, 0.62, 8, r2=0.07), TR((0, 0, 0.2)), "MetalChitauri", 0.9)
    for z in (0.38, 0.6):
        P.add(t_torus(0.105 - (z - 0.38) * 0.1, 0.022, 12, 4), TR((0, 0, z)), "GlowCyan")
    for k in range(3):
        a = k * 2 * math.pi / 3
        d = Vector((math.cos(a), math.sin(a), 0))
        t = Vector((-d.y, d.x, 0)) * 0.015
        fin = [d * 0.1 + Vector((0, 0, 0.2)), d * 0.3 + Vector((0, 0, 0.2)), d * 0.17 + Vector((0, 0, 0.55)),
               d * 0.08 + Vector((0, 0, 0.8))]
        P.add(t_prism([p - t for p in fin], t * 2), None, "RustChitauri", 0.75)
        P.add(t_tube([d * 0.07 + Vector((0, 0, 0.78)), d * 0.16 + Vector((0, 0, 0.88)), d * 0.1 + Vector((0, 0, 1.0))],
                     [0.025, 0.02, 0.008], 4, smooth=False), None, "MetalChitauri", 0.9)
    P.add(t_octa(0.08, 0.12), TR((0, 0, 0.9)), "GlowCyan")
    C.box(-0.3, -0.3, 0, 0.3, 0.3, 1.0)
    ob = P.finish()
    C.attach(ob)
    return ob


# ================================================================ build / export / preview
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    tops, extra = [], []
    for f in (ultron_tower, hover_platform, goo_rim, goo_island, vault_walls, sanctum, vormir_spire, force_pylon):
        tops.append(f())
    base, kids = turret()
    tops.append(base)
    extra += kids
    return tops, extra


def all_objs(tops):
    out = []
    for o in tops:
        out.append(o)
        out += list(o.children_recursive)
    return out


def report(tops):
    total = 0
    print("REPORT piece | tris | godot min | godot max | cols")
    for o in tops:
        meshes = [o] + [c for c in o.children_recursive if c.type == "MESH" and "colonly" not in c.name]
        tris = sum(sum(len(p.vertices) - 2 for p in m.data.polygons) for m in meshes)
        total += tris
        co = [o.matrix_world @ v.co for v in o.data.vertices]
        xs, ys, zs = [c.x for c in co], [c.y for c in co], [c.z for c in co]
        ncol = len([c for c in o.children_recursive if "colonly" in c.name])
        print("REPORT %-16s %6d  min(%.2f, %.2f, %.2f) max(%.2f, %.2f, %.2f) cols=%d" % (
            o.name, tris, min(xs), min(zs), -max(ys), max(xs), max(zs), -min(ys), ncol))
    print("REPORT total tris", total)


def export(tops):
    bpy.ops.object.select_all(action="DESELECT")
    objs = all_objs(tops)
    for o in objs:
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = tops[0]
    path = os.path.join(OUT, "sites.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_cameras=False, export_lights=False,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False)
    for o in objs:
        if "colonly" in o.name:
            o.hide_render = True
    print("EXPORTED", path)


TEXMAP = [("Concrete", "concrete", 0.5), ("Brick", "brick", 0.6), ("Plaster", "plaster", 0.5),
          ("Trim", "plaster", 0.5), ("Rust", "rust", 0.7)]


def preview_materials():
    for name, m in mats.items():
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        base = tuple(bsdf.inputs["Base Color"].default_value)
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(vc.outputs["Color"], mul.inputs["B"])
        hit = next((t for t in TEXMAP if name.startswith(t[0])), None)
        if hit:
            _, tex, sc = hit
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (sc, sc, sc)
            nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])

            def img(fn, non_color=False):
                n = nt.nodes.new("ShaderNodeTexImage")
                n.image = bpy.data.images.load(os.path.join(TEX, fn), check_existing=True)
                if non_color:
                    n.image.colorspace_settings.name = "Non-Color"
                n.projection = "BOX"
                n.projection_blend = 0.25
                nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
                return n
            alb = img(tex + "_albedo.jpg")
            m1 = nt.nodes.new("ShaderNodeMix")
            m1.data_type = "RGBA"
            m1.blend_type = "MULTIPLY"
            m1.inputs["Factor"].default_value = 1.0
            m1.inputs["A"].default_value = base
            nt.links.new(alb.outputs["Color"], m1.inputs["B"])
            nt.links.new(m1.outputs["Result"], mul.inputs["A"])
            nrm = img(tex + "_normal.jpg", True)
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        else:
            mul.inputs["A"].default_value = base
        nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])


def place(o, loc, rot=0.0):
    c = bpy.data.objects.new(o.name + "_pv", o.data)
    bpy.context.collection.objects.link(c)
    c.location = loc
    c.rotation_euler.z = rot
    return c


def place_tree(o, loc, rot=0.0):
    c = place(o, loc, rot)
    for ch in o.children:
        if ch.type == "MESH" and "colonly" not in ch.name:
            cc = place_tree(ch, (0, 0, 0))
            cc.parent = c
            cc.location = ch.location
    return c


def setup_scene():
    scn = bpy.context.scene
    try:
        scn.render.engine = "BLENDER_EEVEE"
    except TypeError:
        scn.render.engine = "BLENDER_EEVEE_NEXT"
    scn.render.resolution_x, scn.render.resolution_y = (2400, 1350)
    try:
        scn.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    world = bpy.data.worlds.new("W")
    scn.world = world
    nt = world.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    hdr = os.path.join(TEX, "wasteland_sky.hdr")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(hdr)
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.7
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.001))
    g = bpy.context.active_object
    gm = bpy.data.materials.new("GroundPV")
    gnt = gm.node_tree
    gb = next(n for n in gnt.nodes if n.type == "BSDF_PRINCIPLED")
    ti = gnt.nodes.new("ShaderNodeTexImage")
    ti.image = bpy.data.images.load(os.path.join(TEX, "pavement_albedo.jpg"))
    tc = gnt.nodes.new("ShaderNodeTexCoord")
    mp = gnt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.35, 0.35, 0.35)
    gnt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    gnt.links.new(mp.outputs["Vector"], ti.inputs["Vector"])
    gnt.links.new(ti.outputs["Color"], gb.inputs["Base Color"])
    gb.inputs["Roughness"].default_value = 0.95
    g.data.materials.append(gm)
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object
    sun.data.energy = 3.2
    sun.data.angle = math.radians(3)
    sun.rotation_euler = (math.radians(50), math.radians(-12), math.radians(-35))
    return scn


def goo_disc(loc, r):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=r, depth=0.05, location=(loc[0], loc[1], 0.05))
    o = bpy.context.active_object
    m = bpy.data.materials.new("GooPV")
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.5, 0.02, 0.02, 1)
    b.inputs["Roughness"].default_value = 0.15
    b.inputs["Emission Color"].default_value = (1, 0.05, 0.02, 1)
    b.inputs["Emission Strength"].default_value = 0.8
    o.data.materials.append(m)


def hero(loc):
    """0.53 m scale figure (not exported)."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.12, depth=0.4, location=(loc[0], loc[1], loc[2] + 0.2))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, location=(loc[0], loc[1], loc[2] + 0.46))
    b = bpy.context.active_object
    m = bpy.data.materials.new("HeroPV")
    bb = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bb.inputs["Base Color"].default_value = (0.1, 0.25, 0.9, 1)
    for o in (a, b):
        o.data.materials.append(m)


def camera(scn, loc, target, lens):
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cd.lens = lens
    cd.clip_end = 600
    scn.camera = cam
    return cam


def render(scn, path):
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


def preview(tops, mode, path):
    by = {o.name: o for o in tops}
    scn = setup_scene()
    for o in all_objs(tops):
        o.hide_render = True
    if mode == "lineup":
        place_tree(by["GooPoolRim"], (-22, 6, 0))
        place_tree(by["GooIsland"], (-22, 6, 0))
        goo_disc((-22, 6), 7.05)
        place_tree(by["Sanctum"], (-3, 10, 0))
        place_tree(by["VaultWalls"], (13, 8, 0))
        place_tree(by["UltronTower"], (26, 4, 0))
        place_tree(by["VormirSpire"], (34, 6, 0))
        place_tree(by["HoverPlatform"], (27.5, -6.5, 4.0))
        place_tree(by["Turret"], (20.5, -6.5, 0), 0.5)
        place_tree(by["ForceFieldPylon"], (17.5, -6.0, 0))
        place_tree(by["ForceFieldPylon"], (23.5, -6.0, 0))
        hero((10.5, -3.0, 0))
        hero((26.0, 1.2, 3.0))
        camera(scn, (6, -42, 22), (6, 4, 1.5), 28)
    elif mode == "interior":
        place_tree(by["Sanctum"], (0, 0, 0))
        hero((-4.7, 0.4, LAND_Z))
        hero((0.5, 4.6, BALC_Z))
        for (x, y, z, e) in ((0, -1, 6.5, 2500), (3, 2, 3, 900), (-3, -3, 3, 700)):
            bpy.ops.object.light_add(type="POINT", location=(x, y, z))
            bpy.context.active_object.data.energy = e
            bpy.context.active_object.data.color = (1, 0.82, 0.62)
            bpy.context.active_object.data.shadow_soft_size = 1.0
        camera(scn, (4.6, -5.2, 2.2), (-1.2, 2.4, 2.6), 14)
    elif mode == "close":
        place_tree(by["UltronTower"], (0, 0, 0))
        place_tree(by["HoverPlatform"], (5.5, -1, 3.0))
        place_tree(by["Turret"], (3.2, -3.5, 0))
        place_tree(by["ForceFieldPylon"], (4.6, -3.6, 0))
        place_tree(by["VormirSpire"], (-5.5, 2, 0))
        hero((2.6, -3.0, 0))
        camera(scn, (1.5, -16, 5.0), (0.5, 0, 3.0), 30)
    elif mode == "front":
        place_tree(by["Sanctum"], (0, 0, 0))
        place_tree(by["VaultWalls"], (14, 2, 0))
        hero((0, -6.5, 0))
        camera(scn, (5, -26, 6), (5, 0, 3.5), 30)
    render(scn, path)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    tops, extra = build()
    report(tops)
    export(tops)
    preview_materials()
    mode = argv[0] if argv else "lineup"
    out = argv[1] if len(argv) > 1 else os.path.join(RENDERS, "sites_kit.png" if mode == "lineup"
                                                     else "sites_kit_%s.png" % mode)
    preview(tops, mode, out)
