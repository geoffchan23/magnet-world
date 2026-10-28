# Post-apocalyptic city kit: modular building pieces + street props.
# Run: blender --background --python art/src/city_kit.py
# Exports assets/city/kit.glb (one top-level mesh object per piece) and a lineup
# preview at art/renders/city_kit_preview.png.
#
# Units are game units (player = 0.55 tall, 1 unit ~ 2.4 m). A storey is 1.25.
# Every piece: origin at the centre of its footprint on the ground (z = 0 at the
# bottom), front faces Blender -Y (= Godot +Z). Building modules are 4 x 4 and
# stay inside x, y in [-2, 2] so they tile side by side and stack vertically.
# Walls sit at +-1.92; bands, pilasters and cornices stick out to exactly +-2.0.
#
# Materials are named so Godot can swap in triplanar PBR textures by name; base
# colours are light tints (Godot multiplies texture x base colour x vertex colour).
# Vertex colour attribute "Col" carries grime/soot darkening.
import bpy, bmesh, math, os, random, sys
from mathutils import Vector, Matrix, Euler, noise

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "assets", "city")
RENDERS = os.path.join(ROOT, "art", "renders")
TEX = os.path.join(ROOT, "assets", "textures")
os.makedirs(OUT, exist_ok=True)
os.makedirs(RENDERS, exist_ok=True)

H = 1.25          # storey height
WO = 1.92         # outer face of main walls
EDGE = 2.0        # footprint half-size (bands/pilasters reach this)
T = 0.16          # wall thickness

# name: (base colour, roughness, metallic)
MAT_DEFS = {
    "Concrete":   ((0.8, 0.84, 0.88, 1), 0.92, 0.0),
    "Brick":      ((0.92, 0.62, 0.52, 1), 0.9, 0.0),
    "Plaster":    ((0.95, 0.88, 0.76, 1), 0.9, 0.0),
    "Glass":      ((0.04, 0.055, 0.065, 1), 0.08, 0.0),
    "Metal":      ((0.62, 0.65, 0.68, 1), 0.5, 0.4),
    "Rust":       ((0.55, 0.3, 0.17, 1), 0.85, 0.25),
    "Wood":       ((0.2, 0.12, 0.065, 1), 0.9, 0.0),
    "Trim":       ((0.09, 0.2, 0.13, 1), 0.75, 0.0),
    "TrimRed":    ((0.55, 0.08, 0.05, 1), 0.75, 0.0),
    "TrimTeal":   ((0.05, 0.3, 0.32, 1), 0.75, 0.0),
    "TrimYellow": ((0.85, 0.52, 0.06, 1), 0.75, 0.0),
    "Interior":   ((0.035, 0.033, 0.038, 1), 0.95, 0.0),
    "Rebar":      ((0.25, 0.14, 0.09, 1), 0.7, 0.6),
}
mats = {}


def mat(name):
    if name in mats:
        return mats[name]
    col, rough, metal = MAT_DEFS[name]
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    mats[name] = m
    return m


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def sstep(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def TR(loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    M = Matrix.Translation(Vector(loc)) @ Euler(rot).to_matrix().to_4x4()
    if scale:
        M = M @ Matrix.Diagonal(Vector((*scale, 1)))
    return M


def side_M(k):
    """Side k: 0 front(-Y), 1 right(+X), 2 back(+Y), 3 left(-X). Front frame -> side."""
    return Matrix.Rotation(k * math.pi / 2, 4, "Z")


# ---------------------------------------------------------------- piece builder
class Piece:
    def __init__(self, name, grime=None):
        self.name = name
        self.bm = bmesh.new()
        self.col = self.bm.loops.layers.color.new("Col")
        self.mats = []
        self.grime = grime or (lambda p, n: 1.0)

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def add(self, tmp, M=None, m="Concrete", tint=1.0, smooth=None):
        """Copy a temp bmesh in; m is a name or a list indexed by face.material_index."""
        M = M if M is not None else Matrix.Identity(4)
        NM = M.to_3x3().inverted().transposed()
        vmap, local = {}, {}
        for v in tmp.verts:
            nv = self.bm.verts.new(M @ v.co)
            vmap[v] = nv
            local[nv] = v.co.copy()
        for f in tmp.faces:
            try:
                nf = self.bm.faces.new([vmap[v] for v in f.verts])
            except ValueError:
                continue
            name = m[f.material_index] if isinstance(m, (list, tuple)) else m
            nf.material_index = self.mi(name)
            nf.smooth = f.smooth if smooth is None else smooth
            n = (NM @ f.normal).normalized()
            for l in nf.loops:
                t = tint(local[l.vert]) if callable(tint) else tint
                if not isinstance(t, (tuple, list)):
                    t = (t, t, t)
                g = self.grime(l.vert.co, n)
                l[self.col] = (clamp(t[0] * g), clamp(t[1] * g), clamp(t[2] * g), 1.0)
        for e in tmp.edges:
            if not e.smooth:
                ne = self.bm.edges.get([vmap[e.verts[0]], vmap[e.verts[1]]])
                if ne:
                    ne.smooth = False
        tmp.free()

    def box(self, x0, y0, z0, x1, y1, z1, m="Concrete", tint=1.0, bevel=0.0, M=None):
        self.add(t_box(x0, y0, z0, x1, y1, z1, bevel), M, m, tint)

    def finish(self, edge=None, recenter=False, height=None):
        bm = self.bm
        if edge is None and self.name.split("_")[0] in ("Brick", "Conc", "Office"):
            edge = EDGE
        for v in bm.verts:
            v.co.z = max(v.co.z, 0.0)
            if edge:
                v.co.x = clamp(v.co.x, -edge, edge)
                v.co.y = clamp(v.co.y, -edge, edge)
        if recenter or height:
            xs = [v.co.x for v in bm.verts]
            ys = [v.co.y for v in bm.verts]
            zs = [v.co.z for v in bm.verts]
            cx = (min(xs) + max(xs)) / 2 if recenter else 0.0
            cy = (min(ys) + max(ys)) / 2 if recenter else 0.0
            k = height / max(zs) if height else 1.0
            for v in bm.verts:
                v.co = Vector(((v.co.x - cx) * k, (v.co.y - cy) * k, v.co.z * k))
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


# ---------------------------------------------------------------- primitives (temp bmeshes)
def t_box(x0, y0, z0, x1, y1, z1, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=1,
                        affect="EDGES", profile=0.5, clamp_overlap=True)
    return bm


def t_prism(base, offset):
    """Polygon (list of 3D points) extruded along offset; closed, normals outward."""
    bm = bmesh.new()
    off = Vector(offset)
    b = [bm.verts.new(Vector(p)) for p in base]
    t = [bm.verts.new(Vector(p) + off) for p in base]
    bm.faces.new(b)
    bm.faces.new(t[::-1])
    n = len(base)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([b[i], b[j], t[j], t[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def t_cyl(r, h, seg=12, r2=None, caps=True, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=h,
                          matrix=Matrix.Translation((0, 0, h / 2)))
    for f in bm.faces:
        f.smooth = smooth and abs(f.normal.z) < 0.95
    for e in bm.edges:
        fs = e.link_faces
        if len(fs) == 2 and fs[0].smooth != fs[1].smooth:
            e.smooth = False
    return bm


def t_bar(p0, p1, r0, r1=None, sides=6, caps=True, smooth=True):
    """Tapered prism between two points (poles, branches, rebar)."""
    bm = bmesh.new()
    p0, p1 = Vector(p0), Vector(p1)
    r1 = r0 if r1 is None else r1
    d = (p1 - p0).normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    u = d.cross(ref).normalized()
    v = d.cross(u).normalized()
    ring0, ring1 = [], []
    for i in range(sides):
        a = 2 * math.pi * (i + 0.5) / sides
        o = u * math.cos(a) + v * math.sin(a)
        ring0.append(bm.verts.new(p0 + o * r0))
        ring1.append(bm.verts.new(p1 + o * r1))
    for i in range(sides):
        j = (i + 1) % sides
        f = bm.faces.new([ring0[i], ring0[j], ring1[j], ring1[i]])
        f.smooth = smooth
    if caps:
        bm.faces.new(ring0[::-1])
        bm.faces.new(ring1)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if caps and smooth:
        for e in bm.edges:
            fs = e.link_faces
            if len(fs) == 2 and fs[0].smooth != fs[1].smooth:
                e.smooth = False
    return bm


def t_tube(pts, radii, sides=6, smooth=True, caps=True):
    """Bent tube through a list of points (one ring per point)."""
    bm = bmesh.new()
    pts = [Vector(p) for p in pts]
    rings = []
    prev_u = None
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        if prev_u is None:
            ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
            u = d.cross(ref).normalized()
        else:
            u = (prev_u - d * prev_u.dot(d)).normalized()
        prev_u = u
        v = d.cross(u).normalized()
        ring = []
        for k in range(sides):
            a = 2 * math.pi * (k + 0.5) / sides
            ring.append(bm.verts.new(p + (u * math.cos(a) + v * math.sin(a)) * radii[i]))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(sides):
            j = (k + 1) % sides
            f = bm.faces.new([a[k], a[j], b[j], b[k]])
            f.smooth = smooth
    if caps:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def t_torus(R, r, seg=12, rseg=6):
    bm = bmesh.new()
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        c = Vector((math.cos(a), math.sin(a), 0))
        ring = []
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            ring.append(bm.verts.new(c * (R + r * math.cos(b)) + Vector((0, 0, r * math.sin(b)))))
        rings.append(ring)
    for i in range(seg):
        a, b = rings[i], rings[(i + 1) % seg]
        for j in range(rseg):
            k = (j + 1) % rseg
            f = bm.faces.new([a[j], b[j], b[k], a[k]])
            f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def t_quad(pts):
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(Vector(p)) for p in pts])
    return bm


def t_shards(u0, u1, z0, z1, y, rng):
    """Window pane with a jagged hole punched through (single-sided, faces -Y)."""
    bm = bmesh.new()
    cx, cz = (u0 + u1) / 2, (z0 + z1) / 2
    w, h = u1 - u0, z1 - z0
    n = 10
    outer, inner = [], []
    for i in range(n):
        a = -math.pi / 2 - 2 * math.pi * i / n   # clockwise from below
        dx, dz = math.cos(a), math.sin(a)
        s = 1.0 / max(abs(dx) / (w / 2), abs(dz) / (h / 2))
        outer.append(Vector((cx + dx * s, y, cz + dz * s)))
        k = rng.uniform(0.35, 0.92) if i % 2 == 0 else rng.uniform(0.15, 0.55)
        inner.append(Vector((cx + dx * s * k + rng.uniform(-0.05, 0.05) * w, y, cz + dz * s * k)))
    ov = [bm.verts.new(p) for p in outer]
    iv = [bm.verts.new(p) for p in inner]
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new([ov[i], ov[j], iv[j], iv[i]])
    for f in bm.faces:
        if f.normal.y > 0:
            f.normal_flip()
    return bm


def t_panel(u0, u1, z0, z1, y0, y1, holes=(), top=None, extra_u=(), extra_z=(), caps="all"):
    """Wall slab in the front frame (outer face at y0 facing -Y, back at y1) with
    rectangular holes (a, b, c, d) = u-range, z-range and an optional jagged top
    profile top(u). Face material index 0 = outer/reveals, 1 = back face."""
    us = sorted(set([u0, u1] + [h[0] for h in holes] + [h[1] for h in holes] + list(extra_u)))
    us = [u for u in us if u0 <= u <= u1]
    zs = sorted(set([z0, z1] + [h[2] for h in holes] + [h[3] for h in holes] + list(extra_z)))
    zs = [z for z in zs if z0 <= z <= z1]
    bm = bmesh.new()
    vf, vb = {}, {}

    def zc(i, j):
        z = zs[j]
        if top is not None:
            z = min(z, max(z0, top(us[i])))
        return round(z, 5)

    def V(i, j, back):
        key = (i, zc(i, j))
        d = vb if back else vf
        if key not in d:
            d[key] = bm.verts.new((us[i], y1 if back else y0, key[1]))
        return d[key]

    nu, nz = len(us) - 1, len(zs) - 1

    def is_hole(i, j):
        cu, cz = (us[i] + us[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
        return any(h[0] <= cu <= h[1] and h[2] <= cz <= h[3] for h in holes)

    def corners(i, j):
        return [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]

    def degenerate(i, j):
        ks = [(a, zc(a, b)) for a, b in corners(i, j)]
        return len(set(ks)) < 3

    def solid(i, j):
        if i < 0 or j < 0 or i >= nu or j >= nz:
            return False
        return not is_hole(i, j) and not degenerate(i, j)

    for i in range(nu):
        for j in range(nz):
            if not solid(i, j):
                continue
            cs = corners(i, j)
            fr, bk = [], []
            for a, b in cs:
                fv, bv = V(a, b, False), V(a, b, True)
                if not fr or fr[-1] is not fv:
                    fr.append(fv)
                    bk.append(bv)
            if fr[0] is fr[-1]:
                fr.pop()
                bk.pop()
            bm.faces.new(fr).material_index = 0
            bm.faces.new(bk[::-1]).material_index = 1
            nbrs = [(i, j - 1), (i + 1, j), (i, j + 1), (i - 1, j)]
            for e in range(4):
                (a0, b0), (a1, b1) = cs[e], cs[(e + 1) % 4]
                fa, fb = V(a0, b0, False), V(a1, b1, False)
                if fa is fb or solid(*nbrs[e]):
                    continue
                ni, nj = nbrs[e]
                outside = ni < 0 or nj < 0 or ni >= nu or nj >= nz
                if outside and caps != "all":
                    if e == 0 and "bottom" not in caps:
                        continue
                    if e == 2 and "top" not in caps:
                        continue
                    if e in (1, 3) and "ends" not in caps:
                        continue
                f = bm.faces.new([fa, V(a0, b0, True), V(a1, b1, True), fb])
                f.material_index = 0
    return bm


# ---------------------------------------------------------------- grime functions
def grime_building(ground=False, base=1.0):
    def g(p, n):
        v = base * (0.9 + 0.1 * noise.noise(p * 1.9))
        if n.z < -0.5:
            v *= 0.72
        if ground:
            v *= 0.55 + 0.45 * sstep(p.z / 0.55)
        else:
            v *= 0.88 + 0.12 * sstep(p.z / 0.35)
        return v
    return g


def grime_prop(h=0.25):
    def g(p, n):
        v = 0.86 + 0.14 * noise.noise(p * 3.1)
        v *= 0.6 + 0.4 * sstep(p.z / h)
        if n.z < -0.5:
            v *= 0.7
        return v
    return g


def soot_tint(wins, extra=None):
    """Darken the wall under each window (drip streaks) and above burned ones."""
    def f(p):
        v = 1.0
        for (a, b, c, d, kind) in wins:
            if a - 0.12 <= p.x <= b + 0.12:
                if c - 0.45 <= p.z <= c + 1e-4:
                    v *= 1 - 0.38 * (1 - (c - p.z) / 0.45)
                if kind in ("burned", "missing") and d - 1e-4 <= p.z <= d + 0.75:
                    v *= 1 - (0.75 if kind == "burned" else 0.3) * (1 - (p.z - d) / 0.75)
        if extra:
            v *= extra(p)
        return v
    return f


def jag_tint(top, depth=0.3, k=0.45):
    """Darken near a broken top edge."""
    def f(p):
        dz = top(p.x) - p.z
        return 1 - k * (1 - clamp(dz / depth))
    return f


def profile(points):
    """Piecewise-linear top profile from (u, z) points."""
    pts = sorted(points)

    def f(u):
        if u <= pts[0][0]:
            return pts[0][1]
        for (a, za), (b, zb) in zip(pts, pts[1:]):
            if a <= u <= b:
                return za + (zb - za) * (u - a) / max(b - a, 1e-9)
        return pts[-1][1]
    return f, [p[0] for p in pts]


def stepped(points, rng=None):
    """Brick-style stepped profile: (u, z) are step starts."""
    pts = []
    for i, (u, z) in enumerate(points):
        if i > 0:
            pts.append((u - 0.012, points[i - 1][1]))
        pts.append((u, z))
    return profile(pts)


# ---------------------------------------------------------------- shared building parts
def ring(P, z0, z1, outer, inner, m, tint=1.0, bevel=0.0):
    """Four non-overlapping boxes forming a band around the footprint."""
    P.box(-outer, -outer, z0, outer, -inner, z1, m, tint, bevel)
    P.box(-outer, inner, z0, outer, outer, z1, m, tint, bevel)
    P.box(-outer, -inner, z0, -inner, inner, z1, m, tint, bevel)
    P.box(inner, -inner, z0, outer, inner, z1, m, tint, bevel)


def corner_L(P, k, z0, z1, a, b, m, out=EDGE, depth=0.22, tint=1.0):
    """L-shaped corner pilaster/quoin at corner k (front-right corner rotated by k)."""
    M = side_M(k)
    P.box(out - a, -out, z0, out, -out + depth, z1, m, tint, M=M)
    P.box(out - depth, -out + depth, z0, out, -out + b, z1, m, tint, M=M)


def interior_core(P, inset, z0, z1):
    r = WO - inset
    bm = t_box(-r, -r, z0, r, r, z1)
    for f in [f for f in bm.faces if abs(f.normal.z) > 0.9]:
        bm.faces.remove(f)
    P.add(bm, None, "Interior", 0.8)
    s = WO - T + 0.01
    P.add(t_box(-s, -s, z0, s, s, z0 + 0.03), None, "Interior", 0.7)


def window(P, k, a, b, c, d, kind, y0, rng, fam, light=False):
    """Window dressing inside a wall opening on side k (front frame coords)."""
    M = side_M(k)
    w = b - a
    if light:
        P.box(a - 0.06, y0 - 0.06, c - 0.06, b + 0.06, y0 + 0.05, c, "Concrete", 0.95, M=M)
    elif fam == "brick":
        P.box(a - 0.06, y0 - 0.06, c - 0.06, b + 0.06, y0 + 0.05, c, "Concrete", 0.95, M=M)
        P.box(a - 0.05, y0 - 0.025, d, b + 0.05, y0 + 0.05, d + 0.09, "Concrete", 0.9, M=M)
    elif fam == "conc":
        P.box(a - 0.07, y0 - 0.07, c - 0.07, b + 0.07, y0 + 0.05, c, "Concrete", 0.95, bevel=0.012, M=M)
        P.box(a - 0.04, y0 - 0.03, d, b + 0.04, y0 + 0.02, d + 0.05, "Concrete", 0.9, M=M)
        P.box(a - 0.04, y0 - 0.03, c, a, y0 + 0.02, d, "Concrete", 0.9, M=M)
        P.box(b, y0 - 0.03, c, b + 0.04, y0 + 0.02, d, "Concrete", 0.9, M=M)
    yf = y0 + 0.06
    ft = 0.035
    if kind in ("glass", "broken", "frame"):
        fm = "Trim" if fam == "brick" else "Metal"
        P.box(a, yf, c, b, yf + 0.04, c + ft, fm, 0.8, M=M)
        P.box(a, yf, d - ft, b, yf + 0.04, d, fm, 0.8, M=M)
        P.box(a, yf, c + ft, a + ft, yf + 0.04, d - ft, fm, 0.8, M=M)
        P.box(b - ft, yf, c + ft, b, yf + 0.04, d - ft, fm, 0.8, M=M)
        mz = c + (d - c) * 0.62
        P.box(a + ft, yf + 0.005, mz - 0.015, b - ft, yf + 0.035, mz + 0.015, fm, 0.8, M=M)
        if kind == "glass":
            P.add(t_quad([(a + ft, yf + 0.02, c + ft), (b - ft, yf + 0.02, c + ft),
                          (b - ft, yf + 0.02, d - ft), (a + ft, yf + 0.02, d - ft)]), M, "Glass", 1.0)
        elif kind == "broken":
            P.add(t_shards(a + ft, b - ft, c + ft, mz - 0.015, yf + 0.02, rng), M, "Glass", 1.0)
            if rng.random() < 0.6:
                P.add(t_quad([(a + ft, yf + 0.02, mz + 0.015), (b - ft, yf + 0.02, mz + 0.015),
                              (b - ft, yf + 0.02, d - ft), (a + ft, yf + 0.02, d - ft)]), M, "Glass", 1.0)
    elif kind == "boarded":
        n = 3 if (d - c) > 0.5 else 2
        for i in range(n):
            zc = c + (d - c) * (i + 0.5) / n + rng.uniform(-0.03, 0.03)
            ang = rng.uniform(-0.18, 0.18)
            bmb = t_box(-w / 2 - 0.06, -0.012, -0.06, w / 2 + 0.06, 0.012, 0.06)
            P.add(bmb, M @ TR(((a + b) / 2, y0 - 0.02 - 0.03 * i % 2 * 0.0, zc), (0, ang, 0)), "Wood",
                  rng.uniform(0.75, 1.0))
    elif kind == "ac":
        P.box(a + 0.06, y0 - 0.075, c + 0.02, a + 0.06 + 0.34, yf + 0.02, c + 0.24, "Metal", 0.85, bevel=0.01, M=M)
        P.box(a + ft, yf, c + 0.24, b - ft, yf + 0.02, d - ft, "Glass", 1.0, M=M)
    # "missing"/"burned": just the dark interior shows through


# ---------------------------------------------------------------- building modules
FAM = {
    "brick": dict(wall="Brick", wins=[(-1.42, -0.82), (-0.3, 0.3), (0.82, 1.42)], wz=(0.3, 1.0)),
    "conc": dict(wall="Plaster", wins=[(-1.45, -0.7), (-0.37, 0.37), (0.7, 1.45)], wz=(0.36, 0.98)),
}


def floor_module(name, fam, seed, kinds):
    rng = random.Random(seed)
    P = Piece(name, grime_building())
    f = FAM[fam]
    wall = f["wall"]
    for k in range(4):
        wins = []
        for i, (a, b) in enumerate(f["wins"]):
            kind = kinds[(k * 3 + i) % len(kinds)]
            wins.append((a, b, f["wz"][0], f["wz"][1], kind))
        holes = [w[:4] for w in wins]
        pb = t_panel(-WO, WO - T, 0, H, -WO, -WO + T, holes, extra_z=[f["wz"][0] - 0.3],
                     caps=("ends",))
        P.add(pb, side_M(k), [wall, "Interior"], soot_tint(wins))
        for (a, b, c, d, kind) in wins:
            window(P, k, a, b, c, d, kind, -WO, rng, fam)
    if fam == "brick":
        ring(P, 0, 0.07, 1.97, WO - 0.02, "Concrete", 0.9)
        for k in range(4):
            for i, (z0, z1) in enumerate([(0.07, 0.42), (0.44, 0.79), (0.81, 1.16)]):
                a, b = (0.34, 0.22) if i % 2 == 0 else (0.22, 0.34)
                corner_L(P, k, z0, z1, a, b, "Concrete", depth=0.12, tint=0.92)
            corner_L(P, k, 1.16, H, 0.08, 0.08, "Brick", out=WO + 0.001, depth=0.08)
    else:
        ring(P, 0, 0.16, EDGE, WO - 0.04, "Concrete", 0.95)
        for k in range(4):
            corner_L(P, k, 0.16, H, 0.26, 0.26, "Concrete", depth=0.26, tint=0.95)
    interior_core(P, T + 0.38, 0, H)
    return P.finish()


def office_floor(name, seed, kinds):
    rng = random.Random(seed)
    P = Piece(name, grime_building())
    ring(P, 0, 0.38, EDGE, 1.8, "Concrete", 0.95)
    # dark soffit/back for the spandrel and a dark ceiling strip
    for k in range(4):
        corner_L(P, k, 0.38, H, 0.3, 0.3, "Concrete", depth=0.3)
        M = side_M(k)
        yg = -1.93
        n = 6
        u0, u1 = -1.7, 1.7
        pw = (u1 - u0) / n
        P.box(u0, yg - 0.03, 0.38, u1, yg + 0.05, 0.43, "Metal", 0.8, M=M)
        P.box(u0, yg - 0.03, H - 0.05, u1, yg + 0.05, H, "Metal", 0.75, M=M)
        for i in range(n + 1):
            u = u0 + i * pw
            if 0 < i < n:
                P.box(u - 0.025, yg - 0.03, 0.43, u + 0.025, yg + 0.05, H - 0.05, "Metal", 0.8, M=M)
        for i in range(n):
            kind = kinds[(k * n + i) % len(kinds)]
            a, b = u0 + i * pw + 0.025, u0 + (i + 1) * pw - 0.025
            if i == 0:
                a = u0
            if i == n - 1:
                b = u1
            c, d = 0.43, H - 0.05
            if kind == "glass":
                P.add(t_quad([(a, yg, c), (b, yg, c), (b, yg, d), (a, yg, d)]), M, "Glass", 1.0)
            elif kind == "broken":
                P.add(t_shards(a, b, c, d, yg, rng), M, "Glass", 1.0)
            elif kind == "boarded":
                for j in range(3):
                    zc = c + (d - c) * (j + 0.5) / 3
                    P.add(t_box(-(b - a) / 2 - 0.02, -0.012, -0.07, (b - a) / 2 + 0.02, 0.012, 0.07),
                          M @ TR(((a + b) / 2, yg - 0.05, zc), (0, rng.uniform(-0.25, 0.25), 0)), "Wood",
                          rng.uniform(0.75, 1))
            elif kind == "soot":
                P.add(t_shards(a, b, c, d, yg, rng), M, "Glass", 0.4)
                P.box(a - 0.02, yg - 0.04, H - 0.05, b + 0.02, yg - 0.035, H, "Metal", 0.35, M=M)
    # thin dark band inside the glass so missing panes show depth
    interior_core(P, 0.55, 0.38, H)
    s = 1.8
    P.add(t_box(-s, -s, 0.36, s, s, 0.4), None, "Interior", 0.7)
    return P.finish()


def shopfront(P, k, fam, layout, rng, sign_mat):
    """Recessed storefront on side k: window + door under a fascia."""
    M = side_M(k)
    flip = layout.get("flip", False)
    ys = -1.62          # storefront glass line (recessed)
    wall = {"brick": "Brick", "conc": "Plaster", "office": "Metal"}[fam]
    win = (-1.42, 0.22) if not flip else (-0.22, 1.42)
    door = (0.42, 0.92) if not flip else (-0.92, -0.42)
    c, d = 0.18, 0.86
    holes = [(win[0], win[1], c, d), (door[0], door[1], 0.0, 0.8)]
    if fam == "office":
        holes = [(-1.5, -0.55, 0.05, 0.86), (-0.42, 0.42, 0.0, 0.86), (0.55, 1.5, 0.05, 0.86)]
    pb = t_panel(-1.6, 1.6, 0, 0.9, ys, ys + 0.12, holes, caps=("ends", "top"))
    soot = [(h[0], h[1], h[2], h[3], layout.get("burn", "x")) for h in holes]
    P.add(pb, M, [wall, "Interior"], soot_tint(soot))
    wk = layout["win"]
    for idx, h in enumerate(holes):
        a, b, c0, d0 = h
        is_door = (h[2] == 0.0)
        kind = layout["door"] if is_door else wk
        if fam == "office":
            kind = layout["office"][idx]
        yf = ys + 0.05
        if kind == "broken":
            P.box(a, yf, c0, b, yf + 0.03, c0 + 0.04, "Metal", 0.8, M=M)
            P.box(a, yf, d0 - 0.04, b, yf + 0.03, d0, "Metal", 0.8, M=M)
            P.add(t_shards(a, b, c0 + 0.04, d0 - 0.04, yf + 0.015, rng), M, "Glass")
        elif kind == "glass":
            P.add(t_quad([(a, yf, c0), (b, yf, c0), (b, yf, d0), (a, yf, d0)]), M, "Glass")
        elif kind == "shutter":
            # half-open corrugated roller shutter + housing
            zb = c0 + (d0 - c0) * rng.uniform(0.35, 0.55) if not is_door else 0.35
            prof = []
            nrib = int((d0 - zb) / 0.045)
            for i in range(nrib + 1):
                z = zb + (d0 - zb) * i / nrib
                prof.append((ys - 0.035 - (0.015 if i % 2 else 0), z))
            base = [(a - 0.02, y, z) for (y, z) in prof] + [(a - 0.02, ys - 0.01, d0), (a - 0.02, ys - 0.01, zb)]
            P.add(t_prism(base, (b - a + 0.04, 0, 0)), M, "Metal", 0.8)
            P.box(a - 0.04, ys - 0.12, d0, b + 0.04, ys, d0 + 0.08, "Metal", 0.7, bevel=0.012, M=M)
            P.box(a - 0.04, ys - 0.06, c0 if not is_door else 0, a - 0.01, ys, d0, "Metal", 0.75, M=M)
            P.box(b + 0.01, ys - 0.06, c0 if not is_door else 0, b + 0.04, ys, d0, "Metal", 0.75, M=M)
            if not is_door:
                P.add(t_shards(a, b, c0, zb, yf + 0.015, rng), M, "Glass", 0.8)
        elif kind == "boarded":
            n = max(2, int((d0 - c0) / 0.17))
            for i in range(n):
                zc = c0 + (d0 - c0) * (i + 0.5) / n
                ang = rng.uniform(-0.12, 0.12)
                P.add(t_box(-(b - a) / 2 - 0.05, -0.012, -0.065, (b - a) / 2 + 0.05, 0.012, 0.065),
                      M @ TR(((a + b) / 2, ys - 0.02, zc), (0, ang, 0)), "Wood", rng.uniform(0.7, 1))
            # an X brace
            P.add(t_box(-0.04, -0.012, -0.5 * (d0 - c0), 0.04, 0.012, 0.5 * (d0 - c0)),
                  M @ TR(((a + b) / 2, ys - 0.045, (c0 + d0) / 2), (0, 0.6, 0)), "Wood", 0.8)
        elif kind == "door":
            # door leaf hanging ajar
            leaf = t_box(0, -0.02, 0.0, (b - a) - 0.02, 0.02, 0.78)
            P.add(leaf, M @ TR((a + 0.01, ys + 0.02, 0.01), (0, 0, -0.7)), layout.get("door_mat", "Trim"), 0.85)
            P.box(a + 0.04, ys + 0.03, 0.0, b - 0.04, ys + 0.05, 0.005, "Interior", 0.5, M=M)
        # "open": nothing
    # sign board on the fascia, awning below it
    sw = rng.uniform(1.7, 2.6)
    sx = rng.uniform(-0.3, 0.3)
    P.box(sx - sw / 2, -EDGE + 0.012, 0.95, sx + sw / 2, -EDGE + 0.05, 1.12, sign_mat, 0.9, bevel=0.012, M=M)
    nl = int(sw / 0.3)
    for i in range(nl):
        if rng.random() < 0.2:
            continue   # missing letter
        lx = sx - sw / 2 + 0.15 + i * (sw - 0.3) / max(nl - 1, 1)
        P.box(lx - 0.07, -EDGE, 0.985, lx + 0.07, -EDGE + 0.012, 1.085, "Plaster", 0.95, M=M)
    if layout.get("awning"):
        aw = layout["awning"]
        a, b = (win if fam != "office" else (-1.5, 1.5))
        n = 3
        for i in range(n):
            u0 = a + (b - a) * i / n
            u1 = a + (b - a) * (i + 1) / n - 0.01
            sag = (0.0, 0.0, 0.0)
            drop = 0.0
            if layout.get("torn") and i == layout["torn"]:
                drop = 0.5
            L = 0.38
            pitch = 0.5 + drop
            strip = t_box(u0, -L, -0.015, u1, 0.0, 0.015)
            P.add(strip, M @ TR((0, ys - 0.0, 0.9), (pitch, 0, 0)), aw, 0.9 if i % 2 else 0.8)
            # valance
            vb = t_box(u0, -0.012, -0.09, u1, 0.012, 0.0)
            ez = 0.9 - L * math.sin(pitch)
            ey = ys - L * math.cos(pitch)
            P.add(vb, M @ TR((0, ey, ez)), aw, 0.75)


def shop_module(name, fam, seed, layouts, signs):
    rng = random.Random(seed)
    P = Piece(name, grime_building(ground=True))
    wall = {"brick": "Brick", "conc": "Plaster", "office": "Concrete"}[fam]
    for k in range(4):
        shopfront(P, k, fam, layouts[k], rng, signs[k])
        # corner piers
        corner_L(P, k, 0, 0.9, 0.4, 0.4, wall if fam != "office" else "Concrete", depth=0.4,
                 tint=0.95)
        if fam == "office":
            M = side_M(k)
            P.box(-0.55, -EDGE, 0, -0.42, -1.62, 0.9, "Concrete", 0.95, M=M)
            P.box(0.42, -EDGE, 0, 0.55, -1.62, 0.9, "Concrete", 0.95, M=M)
    fascia = wall if fam != "office" else "Concrete"
    ring(P, 0.9, 1.15, 1.96, 1.5, fascia, 0.92)
    ring(P, 1.15, H, EDGE, 1.5, "Concrete", 0.95, bevel=0.015 if fam != "office" else 0)
    # plinth step under each storefront
    interior_core(P, 0.75, 0, 0.9)
    s = 1.5
    P.add(t_box(-s, -s, 0.9, s, s, 0.94), None, "Interior", 0.6)
    return P.finish()


def roof_clutter_ac(P, x, y, rot, rng, big=False):
    w, d, h = (0.5, 0.36, 0.32) if not big else (0.8, 0.55, 0.4)
    M = TR((x, y, 0.06), (0, 0, rot))
    P.add(t_box(-w / 2, -d / 2, 0, w / 2, d / 2, h, 0.02), M, "Metal", 0.85)
    P.add(t_cyl(d * 0.36, 0.03, 10), M @ TR((w * 0.18, 0, h)), "Interior", 0.6)
    P.add(t_box(-w / 2 + 0.03, -d / 2 - 0.01, 0.04, -w / 2 + 0.2, d / 2 + 0.01, h - 0.04), M, "Rust", 0.8)
    # pipe into the roof
    P.add(t_tube([(-w / 2, 0, 0.1), (-w / 2 - 0.15, 0, 0.1), (-w / 2 - 0.2, 0, 0.0)], [0.025] * 3, 5), M,
          "Metal", 0.7)


def dish(P, x, y, rot, size=0.22):
    M = TR((x, y, 0.06), (0, 0, rot))
    P.add(t_bar((0, 0, 0), (0, 0, 0.32), 0.022, sides=6), M, "Metal", 0.8)
    D = M @ TR((0, -0.04, 0.38), (math.radians(-60), 0, 0))
    bm = t_cyl(size, size * 0.35, 12, r2=0.02, caps=True)
    P.add(bm, D @ TR((0, 0, size * 0.35), (math.pi, 0, 0)), "Metal", 0.95)
    P.add(t_bar((0, 0, 0.0), (0, 0, size * 0.9), 0.012, sides=4), D, "Metal", 0.6)


def antenna(P, x, y, h, rng):
    M = TR((x, y, 0.06), (rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), rng.uniform(0, 3)))
    P.add(t_bar((0, 0, 0), (0, 0, h), 0.022, 0.014, sides=5), M, "Metal", 0.75)
    for i, z in enumerate([h * 0.62, h * 0.78, h * 0.92]):
        L = 0.32 - i * 0.07
        P.add(t_bar((-L, 0, z), (L, 0, z + rng.uniform(-0.06, 0.06)), 0.01, sides=4, smooth=False), M,
              "Metal", 0.7)
    for (dx, dy) in [(0.28, 0.0), (-0.14, 0.25), (-0.14, -0.25)]:
        P.add(t_bar((0, 0, h * 0.6), (dx * 2, dy * 2, -0.04), 0.004, sides=3, caps=False, smooth=False), M,
              "Metal", 0.5)


def roof_module(name, fam, seed):
    rng = random.Random(seed)
    P = Piece(name, grime_building(base=1.0))
    wall = {"brick": "Brick", "conc": "Plaster", "office": "Concrete"}[fam]
    # slab
    P.add(t_box(-WO, -WO, 0, WO, WO, 0.06), None, "Concrete", 0.85)
    P.add(t_quad([(-WO, -WO, -0.001), (-WO, WO, -0.001), (WO, WO, -0.001), (WO, -WO, -0.001)]), None,
          "Interior", 0.7)
    ph = 0.36
    pt = 0.12
    for k in range(4):
        top = None
        xu = []
        if fam != "office" and k == (seed % 4):
            top, xu = profile([(-WO, ph), (-0.7, ph), (-0.5, 0.18), (-0.2, 0.12), (0.15, 0.22), (0.35, ph),
                               (WO, ph)])
        pb = t_panel(-WO, WO - pt, 0.0, ph, -WO, -WO + pt, [], top=top, extra_u=xu, caps=("ends", "top"))
        P.add(pb, side_M(k), [wall, wall], 1.0)
        # coping
        if top is None:
            P.add(t_box(-EDGE, -EDGE, ph, EDGE - 0.001 - 0.18, -WO + pt + 0.02, ph + 0.06, 0.012),
                  side_M(k), "Concrete" if fam != "office" else "Metal", 0.95)
        else:
            for (u0, u1) in [(-EDGE, -0.7), (0.35, EDGE - 0.18)]:
                P.add(t_box(u0, -EDGE, ph, u1, -WO + pt + 0.02, ph + 0.06, 0.012), side_M(k), "Concrete", 0.95)
        P.add(t_box(EDGE - 0.18, -EDGE, ph, EDGE, -WO + pt + 0.02, ph + 0.06, 0.0), side_M(k),
              "Concrete" if fam != "office" else "Metal", 0.95)
    if fam != "office":
        ring(P, 0, 0.12, EDGE, WO - 0.02, "Concrete", 0.95, bevel=0.0)
    else:
        ring(P, 0, 0.38, EDGE, WO - 0.02, "Concrete", 0.95)
    # clutter
    if fam == "brick":
        # wooden water tank on a steel stand
        tx, ty = 0.75, 0.7
        for (dx, dy) in [(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)]:
            P.add(t_bar((tx + dx, ty + dy, 0.06), (tx + dx * 0.9, ty + dy * 0.9, 0.5), 0.03, sides=4,
                        smooth=False), None, "Rust", 0.8)
        P.add(t_box(tx - 0.38, ty - 0.38, 0.46, tx + 0.38, ty + 0.38, 0.5), None, "Rust", 0.75)
        P.add(t_cyl(0.42, 0.5, 14), TR((tx, ty, 0.5)), "Wood", 0.9)
        for z in (0.6, 0.85):
            P.add(t_cyl(0.43, 0.025, 14), TR((tx, ty, z)), "Rust", 0.7)
        P.add(t_cyl(0.46, 0.18, 14, r2=0.03), TR((tx, ty, 1.0)), "Metal", 0.75)
        P.add(t_tube([(tx - 0.2, ty, 0.5), (tx - 0.2, ty, 0.3), (tx - 0.6, ty - 0.1, 0.12),
                      (tx - 0.9, ty - 0.1, 0.12)], [0.03] * 4, 5), None, "Rust", 0.7)
        # chimney
        P.add(t_box(-1.5, 1.2, 0.06, -1.1, 1.6, 0.62), None, "Brick", soot_tint([], lambda p: 1 - 0.5 * sstep((p.z - 0.4) / 0.2)))
        P.add(t_box(-1.54, 1.16, 0.62, -1.06, 1.64, 0.68, 0.01), None, "Concrete", 0.5)
        roof_clutter_ac(P, -0.6, -0.9, 0.2, rng)
        dish(P, 1.2, -1.2, 0.6)
        antenna(P, -0.5, 0.6, 1.1, rng)
        P.add(t_box(0.0, -0.3, 0.06, 0.45, 0.1, 0.28, 0.015), None, "Metal", 0.8)   # roof hatch
    elif fam == "conc":
        # stair housing with a door
        P.add(t_box(-1.6, 0.5, 0.06, -0.6, 1.6, 0.85), None, "Plaster", lambda p: 0.7 + 0.3 * sstep(p.z / 0.5))
        P.add(t_box(-1.68, 0.42, 0.85, -0.52, 1.68, 0.92, 0.012), None, "Concrete", 0.85)
        P.add(t_box(-1.3, 0.47, 0.06, -0.92, 0.5, 0.64), None, "TrimTeal", 0.8)
        roof_clutter_ac(P, 0.4, -0.8, 0.0, rng)
        roof_clutter_ac(P, 1.1, -0.8, 0.0, rng)
        roof_clutter_ac(P, 0.9, 0.7, 1.57, rng)
        dish(P, -1.2, -1.2, -0.4, 0.26)
        antenna(P, 0.3, 1.2, 1.0, rng)
        # vent pipes
        for (x, y) in [(-0.2, 0.2), (-0.1, 0.35)]:
            P.add(t_cyl(0.05, 0.3, 8), TR((x, y, 0.06)), "Rust", 0.8)
    else:
        # mechanical penthouse with louvres
        P.add(t_box(-1.3, -0.2, 0.06, 0.3, 1.3, 0.95, 0.015), None, "Concrete", lambda p: 0.75 + 0.25 * sstep(p.z / 0.5))
        for i in range(5):
            z = 0.25 + i * 0.12
            P.add(t_box(-1.1, -0.24, z, 0.1, -0.2, z + 0.06), None, "Metal", 0.8)
        P.add(t_box(-1.36, -0.26, 0.95, 0.36, 1.36, 1.0), None, "Metal", 0.8)
        roof_clutter_ac(P, 0.9, -1.1, 0.0, rng, big=True)
        roof_clutter_ac(P, -0.4, -1.2, 0.0, rng, big=True)
        roof_clutter_ac(P, 1.1, 0.4, 1.57, rng)
        dish(P, 1.2, 1.3, 2.5, 0.28)
        antenna(P, -0.8, 0.5, 1.2, rng)
    return P.finish()


# ---------------------------------------------------------------- ruins
def rubble_chunks(P, rng, cx, cy, spread, n, z=0.06, mats=("Concrete",), size=(0.08, 0.28), tilt=1.0,
                  tint=(0.75, 1.0), M=None):
    M = M if M is not None else Matrix.Identity(4)
    for i in range(n):
        s = rng.uniform(*size)
        sx, sy, sz = s * rng.uniform(0.7, 1.5), s * rng.uniform(0.6, 1.2), s * rng.uniform(0.35, 0.8)
        r = spread * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        zz = z + sz * 0.3 + (spread - r) / spread * spread * 0.18 * rng.random()
        rot = (rng.uniform(-0.5, 0.5) * tilt, rng.uniform(-0.5, 0.5) * tilt, rng.uniform(0, 3.14))
        m = rng.choice(mats)
        bev = 0.012 if m != "Brick" else 0.0
        if m == "Brick":
            sx, sy, sz = 0.11, 0.055, 0.04
        P.add(t_box(-sx / 2, -sy / 2, -sz / 2, sx / 2, sy / 2, sz / 2, bev), M @ TR((x, y, zz), rot), m,
              rng.uniform(*tint))


def rebar_spray(P, rng, p, direction, n, length=(0.15, 0.35), spread=0.12, M=None, droop=0.5):
    """A few bent rebar rods poking out of a broken edge at point p, in a direction."""
    M = M if M is not None else Matrix.Identity(4)
    p = Vector(p)
    d = Vector(direction).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 0.1:
        side = Vector((1, 0, 0))
    side.normalize()
    for i in range(n):
        o = p + side * rng.uniform(-spread, spread) + Vector((0, 0, rng.uniform(-0.02, 0.02)))
        L = rng.uniform(*length)
        bend = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), -rng.uniform(0, droop)))
        mid = o + d * L * 0.55
        end = mid + (d + bend).normalized() * L * 0.5
        P.add(t_tube([o - d * 0.03, mid, end], [0.013] * 3, 3, smooth=False, caps=False), M, "Rebar", 0.85)


def jagged_slab(rng, x0, x1, y0, y1, th, jag_side="y0", n=7, amp=0.35):
    """Slab outline (XY) with one broken jagged edge; returns prism bmesh (z 0..th)."""
    pts = []
    if jag_side == "y0":
        pts.append((x1, y1))
        pts.append((x0, y1))
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            j = rng.uniform(0, amp) if 0 < i < n else rng.uniform(0, amp * 0.5)
            pts.append((x + (rng.uniform(-0.08, 0.08) if 0 < i < n else 0), y0 + j))
    else:  # jagged on x1
        pts.append((x0, y0))
        for i in range(n + 1):
            y = y0 + (y1 - y0) * i / n
            j = rng.uniform(0, amp) if 0 < i < n else rng.uniform(0, amp * 0.5)
            pts.append((x1 - j, y + (rng.uniform(-0.08, 0.08) if 0 < i < n else 0)))
        pts.append((x0, y1))
    return t_prism([(x, y, 0) for x, y in pts], (0, 0, th)), pts


def ruin_wall(P, k, fam, top, xu, wins_kinds, rng, back="Plaster", storeys=2, u0=-WO, u1=WO - T):
    f = FAM[fam]
    wins = []
    holes = []
    for s in range(storeys):
        for i, (a, b) in enumerate(f["wins"]):
            kind = wins_kinds[(s * 3 + i) % len(wins_kinds)]
            c, d = f["wz"][0] + s * H, f["wz"][1] + s * H
            if top(a) - 0.15 < c and top(b) - 0.15 < c:
                continue
            holes.append((a, b, c, d))
            wins.append((a, b, c, d, kind))
    zs = [f["wz"][0] - 0.3 + s * H for s in range(storeys)] + [H]
    pb = t_panel(u0, u1, 0, H * storeys + 0.3, -WO, -WO + T, holes, top=top, extra_u=xu, extra_z=zs,
                 caps=("ends", "top"))
    P.add(pb, side_M(k), [f["wall"], back], soot_tint(wins, jag_tint(top)))
    for (a, b, c, d, kind) in wins:
        if top(a) > d + 0.1 and top(b) > d + 0.1:
            window(P, k, a, b, c, d, kind, -WO, rng, fam, light=True)
    return wins


def band_under_top(P, k, top, z0, z1, out, inn, m, u0=-WO, u1=WO):
    """Horizontal band on side k, only where the wall is still standing above it."""
    us = [u0 + (u1 - u0) * i / 40 for i in range(41)]
    seg = None
    segs = []
    for u in us:
        ok = top(u) >= z1
        if ok and seg is None:
            seg = [u, u]
        elif ok:
            seg[1] = u
        elif seg is not None:
            segs.append(seg)
            seg = None
    if seg:
        segs.append(seg)
    for a, b in segs:
        if b - a > 0.1:
            P.box(a, -out, z0, b, -inn, z1, m, 0.9, M=side_M(k))


def ruin_floor(P, rng, fam, hole=None):
    """Floor slab on top of the storey below + rubble scattered on it."""
    s = WO - 0.01
    if hole is None:
        P.add(t_box(-s, -s, 0, s, s, 0.06), None, "Concrete", 0.8)
    else:
        hx0, hy0, hx1, hy1 = hole
        for (a, b, c, d) in [(-s, -s, s, hy0), (-s, hy1, s, s), (-s, hy0, hx0, hy1), (hx1, hy0, s, hy1)]:
            P.add(t_box(a, b, 0, c, d, 0.06), None, "Concrete", 0.8)
        P.add(t_box(hx0, hy0, 0.0, hx1, hy1, 0.01), None, "Interior", 0.5)


def brick_ruin(name, seed):
    rng = random.Random(seed)
    P = Piece(name, grime_building())
    ruin_floor(P, rng, "brick")
    tops = {
        0: stepped([(-WO, 1.95), (-1.25, 1.62), (-0.55, 1.32), (-0.1, 0.95), (0.55, 0.62), (1.1, 0.35), (1.6, 0.22)]),
        3: stepped([(-WO, 0.3), (-1.4, 0.55), (-0.9, 1.0), (-0.3, 1.45), (0.4, 1.8), (1.1, 2.15), (1.5, 2.3)]),
        2: stepped([(-WO, 2.3), (-1.1, 2.45), (-0.4, 2.2), (0.3, 1.9), (0.9, 1.55), (1.4, 1.2)]),
        1: stepped([(-WO, 1.15), (-1.3, 0.8), (-0.6, 0.5), (0.2, 0.3), (0.9, 0.42), (1.4, 0.3)]),
    }
    kinds = ["missing", "broken", "frame", "missing", "boarded", "burned"]
    for k, (top, xu) in tops.items():
        ruin_wall(P, k, "brick", top, xu, kinds[k:] + kinds[:k], rng)
        band_under_top(P, k, top, 0, 0.07, 1.97, WO - 0.02, "Concrete")
        band_under_top(P, k, top, H, H + 0.07, 1.97, WO - 0.02, "Concrete")
    # quoins: tall front-left corner (k=3), stubs on the low corners
    for i, (z0, z1) in enumerate([(0.07, 0.42), (0.44, 0.79), (0.81, 1.16), (1.32, 1.67)]):
        a, b = (0.34, 0.22) if i % 2 == 0 else (0.22, 0.34)
        corner_L(P, 3, z0, z1, a, b, "Concrete", depth=0.12, tint=0.92)
    for k in (0, 1, 2):
        corner_L(P, k, 0.07, 0.2, 0.34, 0.22, "Concrete", depth=0.12, tint=0.85)
    # wooden upper floor: joists + boards, remnant along the back wall, rest hanging down
    hinge_y = 0.75
    for i in range(7):
        x = -1.6 + i * 0.5
        L = rng.uniform(0.0, 0.35)
        P.box(x - 0.04, hinge_y - L, H - 0.12, x + 0.04, WO - T, H, "Wood", 0.75)
    P.box(-WO + T, hinge_y + 0.1, H, WO - T, WO - T, H + 0.03, "Wood", 0.85)
    # the collapsed section: boards on joists hinged at hinge_y, falling to the floor
    ang = math.radians(33)
    Mh = TR((0, hinge_y + 0.1, H + 0.02), (ang, 0, 0))
    for i in range(6):
        x = -1.55 + i * 0.52 + rng.uniform(-0.05, 0.05)
        L = rng.uniform(1.6, 2.25)
        P.add(t_box(x - 0.04, -L, -0.12, x + 0.04, 0, 0), Mh, "Wood", 0.65)
    for j in range(9):
        y = -0.12 - j * 0.24
        x0 = -1.7 + rng.uniform(0, 0.3) * (j > 4)
        x1 = 1.65 - rng.uniform(0, 0.6) * (j > 5)
        if j == 8:
            x0, x1 = -0.9, 0.4
        P.add(t_box(x0, y - 0.11, 0, x1, y + 0.11, 0.025), Mh @ TR((0, 0, 0), (0, rng.uniform(-0.03, 0.03), rng.uniform(-0.02, 0.02))),
              "Wood", rng.uniform(0.7, 0.95))
    # loose planks + brick rubble on the ground floor
    rubble_chunks(P, rng, 0.2, -1.1, 0.8, 22, mats=("Brick", "Brick", "Concrete"), size=(0.1, 0.25))
    rubble_chunks(P, rng, -1.2, 0.3, 0.45, 10, mats=("Brick", "Concrete"), size=(0.1, 0.22))
    P.add(t_box(-0.6, -0.04, -0.02, 0.6, 0.04, 0.02), TR((1.0, 0.3, 0.12), (0.1, 0.3, 0.8)), "Wood", 0.7)
    P.add(t_box(-0.5, -0.04, -0.02, 0.5, 0.04, 0.02), TR((-0.6, -1.3, 0.1), (0.0, -0.15, -0.4)), "Wood", 0.7)
    return P.finish()


def conc_ruin(name, seed, variant):
    rng = random.Random(seed)
    P = Piece(name, grime_building())
    kinds = ["missing", "broken", "missing", "burned", "frame", "missing", "boarded"]
    if variant == 1:
        tops = {
            2: profile([(-WO, 2.35), (-1.3, 2.5), (-0.7, 2.1), (-0.3, 2.25), (0.3, 1.7), (0.8, 1.85), (1.3, 1.3), (WO, 1.1)]),
            1: profile([(-WO, 0.7), (-1.2, 0.95), (-0.5, 0.6), (0.2, 1.1), (0.7, 1.4), (1.3, 1.9), (WO, 2.0)]),
            0: profile([(-WO, 0.9), (-1.4, 0.6), (-0.8, 0.75), (-0.2, 0.35), (0.6, 0.3), (1.2, 0.45), (WO, 0.6)]),
            3: profile([(-WO, 1.2), (-1.0, 1.6), (-0.4, 1.4), (0.3, 1.9), (0.9, 2.2), (1.5, 2.4), (WO, 2.3)]),
        }
    else:
        tops = {
            0: profile([(-WO, 2.45), (-1.4, 2.3), (-1.0, 2.4), (-0.6, 1.7), (-0.2, 1.2), (0.3, 0.7), (0.9, 0.5), (WO, 0.35)]),
            3: profile([(-WO, 0.4), (-1.1, 0.6), (-0.3, 0.9), (0.3, 1.5), (1.0, 2.0), (1.5, 2.5), (WO, 2.45)]),
            2: profile([(-WO, 0.6), (-1.2, 0.45), (-0.2, 0.3), (0.6, 0.55), (1.3, 0.4), (WO, 0.5)]),
            1: profile([(-WO, 0.45), (-1.0, 0.3), (0.0, 0.2), (0.8, 0.4), (1.4, 0.3), (WO, 0.35)]),
        }
    for k, (top, xu) in tops.items():
        xu = sorted(set(xu))
        ruin_wall(P, k, "conc", top, xu, kinds[k:] + kinds[:k], rng)
        band_under_top(P, k, top, 0, 0.16, EDGE, WO - 0.04, "Concrete")
        band_under_top(P, k, top, H, H + 0.16, EDGE, WO - 0.04, "Concrete")
        # rebar sticking up out of the broken wall top
        for u in (-1.2, -0.3, 0.6, 1.4):
            z = top(u)
            if z > 0.5:
                rebar_spray(P, rng, (u, -WO + T / 2, z - 0.05), (0, 0, 1), 2, (0.12, 0.25), 0.1,
                            M=side_M(k), droop=0.2)
    if variant == 1:
        # upper slab: ledge on the back half + hinged slab dropping to the front
        ruin_floor(P, rng, "conc")
        ledge, pts = jagged_slab(rng, -WO + T, WO - T, 0.4, WO - T, 0.12, "y0", 6, 0.3)
        P.add(ledge, TR((0, 0, H)), "Concrete", 0.85)
        for (x, y) in pts[3:-1]:
            rebar_spray(P, rng, (x, y, H + 0.06), (0, -1, 0), 2, (0.15, 0.3), 0.1)
        slab, spts = jagged_slab(rng, -1.6, 1.3, -1.95, 0.0, 0.12, "y0", 6, 0.35)
        Mh = TR((0, 0.42, H + 0.05), (math.radians(31), math.radians(-4), 0))
        P.add(slab, Mh, "Concrete", lambda p: 0.7 + 0.2 * sstep((p.y + 2) / 1.5))
        for (x, y) in spts[3:-1]:
            rebar_spray(P, rng, (x, y, 0.06), (0, -1, 0), 2, (0.12, 0.28), 0.1, M=Mh)
        rubble_chunks(P, rng, -0.1, -1.3, 0.75, 12, size=(0.1, 0.3))
        rubble_chunks(P, rng, 1.2, -0.6, 0.4, 7, size=(0.08, 0.2), mats=("Concrete", "Plaster"))
    else:
        # floor with a hole; a pancaked slab corner propped against the tall corner
        ruin_floor(P, rng, "conc", hole=(0.2, -0.3, 1.3, 0.9))
        slab, spts = jagged_slab(rng, -WO + T, 0.2, -WO + T, 0.6, 0.12, "x1", 6, 0.4)
        P.add(slab, TR((0, 0, H)), "Concrete", 0.85)
        for (x, y) in spts[1:-1]:
            rebar_spray(P, rng, (x, y, H + 0.06), (1, 0, 0), 2, (0.15, 0.3), 0.1)
        s2, s2pts = jagged_slab(rng, -1.0, 0.85, -0.9, 0.9, 0.12, "x1", 5, 0.3)
        Ms = TR((0.75, 0.35, 0.55), (math.radians(8), math.radians(-28), math.radians(20)))
        P.add(s2, Ms, "Concrete", 0.72)
        for (x, y) in s2pts[1:-1]:
            rebar_spray(P, rng, (x, y, 0.06), (1, 0, 0), 2, (0.12, 0.25), 0.1, M=Ms)
        # broken column stub with rebar cage
        P.add(t_box(1.0, 1.0, 0.06, 1.3, 1.3, 0.85), None, "Concrete", jag_tint(lambda u: 0.85, 0.2))
        for (dx, dy) in [(0.04, 0.04), (0.26, 0.04), (0.04, 0.26), (0.26, 0.26)]:
            rebar_spray(P, rng, (1.0 + dx, 1.0 + dy, 0.8), (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1), 1,
                        (0.3, 0.45), 0.0, droop=0.6)
        rubble_chunks(P, rng, -0.8, 0.8, 0.7, 16, size=(0.1, 0.3))
        rubble_chunks(P, rng, 1.4, -1.2, 0.4, 8, size=(0.08, 0.2))
    return P.finish()


def office_ruin(name, seed, variant):
    rng = random.Random(seed)
    P = Piece(name, grime_building())
    ruin_floor(P, rng, "office")
    cols = [(-1.85, -1.85), (0.0, -1.85), (1.85, -1.85), (-1.85, 0.0), (1.85, 0.0),
            (-1.85, 1.85), (0.0, 1.85), (1.85, 1.85), (0.0, 0.0)]
    if variant == 1:
        heights = [2.5, 1.6, 0.6, 2.5, 1.0, 2.5, 2.5, 1.9, 1.4]
    else:
        heights = [0.7, 0.4, 2.5, 1.3, 2.5, 1.0, 2.5, 2.5, 2.5]
    cs = 0.15
    for (x, y), h in zip(cols, heights):
        x0, x1 = max(-EDGE, x - cs), min(EDGE, x + cs)
        y0, y1 = max(-EDGE, y - cs), min(EDGE, y + cs)
        if h < 2.4:
            # broken: jagged slanted top, rebar cage sticking out
            P.add(t_box(x0, y0, 0.06, x1, y1, h), None, "Concrete", jag_tint(lambda u, h=h: h, 0.3))
            for (dx, dy) in [(0.05, 0.05), (-0.05, 0.05), (0.05, -0.05), (-0.05, -0.05)]:
                rebar_spray(P, rng, (x + dx, y + dy, h - 0.04),
                            (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 1), 1, (0.2, 0.4), 0.0, droop=0.7)
        else:
            P.add(t_box(x0, y0, 0.06, x1, y1, h), None, "Concrete", 0.95)
    # spandrel band at the bottom: survives as broken segments
    for k in range(4):
        segs = [(-1.7, -0.4), (0.2, 1.7)] if (k + variant) % 2 else [(-1.7, 0.9)]
        for (a, b) in segs:
            P.box(a, -EDGE, 0.06, b, -1.8, 0.38, "Concrete", 0.95, M=side_M(k))
    upper = []
    if variant == 1:
        # slab at storey 2 over the back/left part, collapsed slab front-right
        ledge, pts = jagged_slab(rng, -EDGE, EDGE, 0.0, EDGE, 0.14, "y0", 7, 0.45)
        P.add(ledge, TR((0, 0, H)), "Concrete", 0.88)
        for (x, y) in pts[3:-1]:
            rebar_spray(P, rng, (x, y, H + 0.07), (0, -1, 0), 2, (0.15, 0.3), 0.1)
        # spandrel on second storey back
        P.box(-EDGE, 1.8, H + 0.14, EDGE, EDGE, H + 0.45, "Concrete", 0.95)
        P.box(-EDGE, -0.2, H + 0.14, -1.8, 1.8, H + 0.45, "Concrete", 0.95)
        slab, spts = jagged_slab(rng, -1.2, 1.8, -1.95, 0.0, 0.14, "y0", 6, 0.4)
        Mh = TR((0, 0.05, H + 0.07), (math.radians(30), math.radians(6), 0))
        P.add(slab, Mh, "Concrete", lambda p: 0.7 + 0.2 * sstep((p.y + 2) / 1.5))
        for (x, y) in spts[3:-1]:
            rebar_spray(P, rng, (x, y, 0.07), (0, -1, 0), 2, (0.12, 0.28), 0.1, M=Mh)
        # remnant glass on the second floor (back wall)
        for i in range(3):
            a = -1.7 + i * 0.57
            P.add(t_shards(a, a + 0.55, H + 0.45, 2.45, -1.93, rng), side_M(2), "Glass", 0.8)
            P.box(a + 0.55, -1.97, H + 0.45, a + 0.6, -1.9, 2.45, "Metal", 0.8, M=side_M(2))
        P.box(-1.85, -EDGE, 2.36, 1.85, -1.8, 2.5, "Concrete", jag_tint(lambda u: 2.5, 0.2), M=side_M(2))
        rubble_chunks(P, rng, 0.4, -1.3, 0.7, 16, size=(0.1, 0.3))
    else:
        # two storeys of slab on the back-right, twisted slab hanging off it
        ledge, pts = jagged_slab(rng, -0.6, EDGE, -0.4, EDGE, 0.14, "y0", 6, 0.4)
        P.add(ledge, TR((0, 0, H)), "Concrete", 0.88)
        top2, pts2 = jagged_slab(rng, -0.1, EDGE, 0.5, EDGE, 0.14, "y0", 5, 0.35)
        P.add(top2, TR((0, 0, 2.36)), "Concrete", 0.88)
        for (x, y) in pts[3:-1]:
            rebar_spray(P, rng, (x, y, H + 0.07), (0, -1, 0), 2, (0.15, 0.3), 0.1)
        for (x, y) in pts2[3:-1]:
            rebar_spray(P, rng, (x, y, 2.43), (0, -1, 0), 2, (0.15, 0.3), 0.1)
        # second storey spandrels
        P.box(-0.6, 1.8, H + 0.14, EDGE, EDGE, H + 0.45, "Concrete", 0.95)
        P.box(1.8, -0.4, H + 0.14, EDGE, 1.8, H + 0.45, "Concrete", 0.95)
        slab, spts = jagged_slab(rng, -1.65, 0.0, -1.6, 1.7, 0.14, "x1", 6, 0.4)
        Mh = TR((-0.55, 0.1, H + 0.07), (0, math.radians(-34), 0))
        P.add(slab, Mh @ TR((0.0, 0, 0)), "Concrete", 0.75)
        for (x, y) in spts[1:-1]:
            pass
        # bent steel beam
        P.add(t_tube([(1.8, -1.8, H), (0.8, -1.7, H + 0.05), (0.1, -1.5, 0.8), (-0.3, -1.3, 0.2)],
                     [0.05] * 4, 4, smooth=False), None, "Rust", 0.8)
        for i in range(3):
            a = -0.0 + i * 0.6
            P.add(t_shards(a, a + 0.55, H + 0.45, 2.3, -1.93, rng), side_M(1), "Glass", 0.8)
        rubble_chunks(P, rng, -0.9, -0.6, 0.8, 18, size=(0.1, 0.3))
    return P.finish()


# ---------------------------------------------------------------- props
def car_wreck_a():
    rng = random.Random(11)
    P = Piece("Car_Wreck_A", grime_prop(0.3))
    W, L = 0.8, 1.9
    # lower body: chamfered, sagging on flat tyres
    body = t_box(-W / 2, -L / 2, 0.12, W / 2, L / 2, 0.38, 0.05)
    for v in body.verts:
        if v.co.y < -0.6 and v.co.z > 0.3:
            v.co.z -= 0.04       # hood slopes down
    P.add(body, TR((0, 0, 0), (0.02, 0.03, 0)), "Rust", lambda p: 0.85 + 0.15 * noise.noise(p * 4))
    # cabin: trapezoid with glass sides
    cab = t_box(-W / 2 + 0.05, -0.35, 0.38, W / 2 - 0.05, 0.45, 0.58, 0.02)
    for v in cab.verts:
        if v.co.z > 0.5:
            v.co.y = v.co.y * 0.72 + 0.04
            v.co.x *= 0.88
    P.add(cab, TR((0, 0, 0), (0.02, 0.03, 0)), "Glass", 0.9)
    roof = t_box(-W / 2 + 0.08, -0.24, 0.56, W / 2 - 0.08, 0.36, 0.6, 0.015)
    P.add(roof, TR((0, 0, -0.01), (0.02, 0.03, 0)), "Rust", 0.8)
    # pillars
    for x in (-W / 2 + 0.07, W / 2 - 0.07):
        for (y0, y1) in [(-0.37, -0.24), (0.36, 0.47)]:
            P.add(t_bar((x * 0.98, y0, 0.38), (x * 0.9, y1 if y1 < 0 else y0 + (y1 - y0) * 0.1, 0.59), 0.025,
                        sides=4, smooth=False), TR((0, 0, 0), (0.02, 0.03, 0)), "Rust", 0.8)
    # broken windscreen hole -> interior dark patch
    P.add(t_quad([(-0.25, -0.36, 0.41), (0.25, -0.36, 0.41), (0.2, -0.27, 0.53), (-0.2, -0.27, 0.53)]),
          TR((0, -0.005, 0.0), (0.02, 0.03, 0)), "Interior", 0.6)
    # bumpers, lights
    P.box(-W / 2 + 0.02, -L / 2 - 0.04, 0.12, W / 2 - 0.02, -L / 2 + 0.02, 0.2, "Metal", 0.75, 0.015)
    P.box(-W / 2 + 0.02, L / 2 - 0.02, 0.12, W / 2 - 0.02, L / 2 + 0.04, 0.2, "Metal", 0.75, 0.015)
    for x in (-0.28, 0.28):
        P.box(x - 0.08, -L / 2 - 0.01, 0.25, x + 0.08, -L / 2 + 0.02, 0.31, "Glass", 0.9)
        P.box(x - 0.08, L / 2 - 0.02, 0.26, x + 0.08, L / 2 + 0.01, 0.31, "TrimRed", 0.7)
    # flat tyres
    for (x, y) in [(-W / 2 + 0.03, -0.58), (W / 2 - 0.03, -0.58), (-W / 2 + 0.03, 0.6), (W / 2 - 0.03, 0.6)]:
        t = t_cyl(0.155, 0.12, 12)
        for v in t.verts:
            v.co.z -= 0.06
        for v in t.verts:
            r = math.hypot(v.co.x, v.co.y)
            if v.co.y < -0.08:
                v.co.y = -0.08 - (v.co.y + 0.08) * 0.25
        P.add(t, TR((x, y, 0.105), (0, math.pi / 2, 0)), "Interior", 0.9)
        P.add(t_cyl(0.08, 0.125, 8), TR((x + (0.003 if x > 0 else -0.003), y, 0.105), (0, math.pi / 2, 0)) @ TR((0, 0, -0.0625)),
              "Rust", 0.7)
    return P.finish(recenter=True)


def car_wreck_b():
    """Boxy van lying on its side, missing a door."""
    rng = random.Random(12)
    P = Piece("Car_Wreck_B", grime_prop(0.25))
    L, W, Hh = 1.95, 0.8, 0.82
    # build upright (wheels at z=0), then tip onto its left side
    place = TR((Hh / 2, 0, W / 2), (0, math.radians(-88), 0))
    # note: after tipping, upright x -> -z ... we position so it rests on the ground
    def M(m=None):
        return place @ (m if m is not None else Matrix.Identity(4))
    body = t_box(-W / 2, -L / 2, 0.14, W / 2, L / 2 - 0.0, Hh, 0.05)
    for v in body.verts:
        if v.co.y < -L / 2 + 0.3 and v.co.z > 0.5:
            v.co.y += 0.22 * (v.co.z - 0.5) / (Hh - 0.5)
    P.add(body, M(), "TrimTeal", lambda p: 0.75 + 0.25 * noise.noise(p * 5))
    # rust patches on the lower body
    P.add(t_box(-W / 2 - 0.005, -0.6, 0.15, W / 2 + 0.005, 0.2, 0.3), M(), "Rust", 0.8)
    P.add(t_box(-0.33, -0.015, -0.14, 0.33, 0.015, 0.14), M(TR((0, -L / 2 + 0.145, 0.62), (-0.31, 0, 0))), "Glass", 0.9)
    for x in (-0.25, 0.25):
        P.add(t_box(x - 0.08, -0.015, -0.04, x + 0.08, 0.015, 0.04), M(TR((0, -L / 2 + 0.07, 0.36), (-0.31, 0, 0))), "Glass", 0.9)
    # windows (dark) - front and side strips
    P.add(t_box(-W / 2 + 0.06, -L / 2 + 0.12, 0.52, W / 2 - 0.06, -L / 2 + 0.2, 0.76), M(TR((0, 0.0, 0)) ), "Glass", 0.9)
    for s in (-1, 1):
        P.add(t_box(s * W / 2 - 0.01, -0.75, 0.52, s * W / 2 + 0.01, 0.75, 0.74), M(), "Glass", 0.9)
    # missing sliding door (top side after tipping = +x upright side) -> dark hole
    P.add(t_box(W / 2 - 0.0, -0.2, 0.18, W / 2 + 0.012, 0.45, 0.72), M(), "Interior", 0.7)
    # wheels
    for (x, y) in [(-W / 2 + 0.07, -0.6), (W / 2 - 0.07, -0.6), (-W / 2 + 0.07, 0.62), (W / 2 - 0.07, 0.62)]:
        P.add(t_cyl(0.15, 0.11, 10), M(TR((x - 0.055, y, 0.15), (0, math.pi / 2, 0))), "Interior", 0.9)
        P.add(t_cyl(0.075, 0.114, 8), M(TR((x - 0.057, y, 0.15), (0, math.pi / 2, 0))), "Rust", 0.75)
    P.box(-W / 2 + 0.02, -L / 2 - 0.04, 0.14, W / 2 - 0.02, -L / 2 + 0.02, 0.24, "Rust", 0.6, 0.015, M=M())
    # the fallen-off door lying next to it
    P.add(t_box(-0.33, -0.3, 0, 0.33, 0.3, 0.03, 0.01), TR((0.95, 0.3, 0.0), (0.05, 0.0, 0.3)), "TrimTeal", 0.75)
    return P.finish(recenter=True)


def bus_wreck():
    rng = random.Random(13)
    P = Piece("Bus_Wreck", grime_prop(0.4))
    L, W, Hb = 4.05, 1.05, 1.3
    z0 = 0.2
    burn = lambda p: (0.45 + 0.55 * (1 - sstep((p.z - 0.7) / 0.5))) * (0.85 + 0.15 * noise.noise(p * 3))
    # sides as panels with window holes (rotated so u runs along the bus)
    wins = []
    for i in range(7):
        a = -L / 2 + 0.72 + i * 0.47
        wins.append((a, a + 0.38, 0.72, 1.12))
    for s in (0, 2):
        M = Matrix.Rotation(math.pi / 2 + s * math.pi / 2, 4, "Z")
        # front frame y0 = -W/2 -> rotated
        pb = t_panel(-L / 2, L / 2, z0, Hb - 0.08, -W / 2, -W / 2 + 0.05, wins if s == 0 else
                     [(-w[1], -w[0], w[2], w[3]) for w in wins] + [(L / 2 - 0.62, L / 2 - 0.18, z0 + 0.06, 1.12)],
                     caps=("ends", "top", "bottom"))
        P.add(pb, M, ["TrimYellow", "Interior"], burn)
    # front & back panels
    for s in (1, 3):
        M = Matrix.Rotation(math.pi / 2 + s * math.pi / 2, 4, "Z")
        holes = [(-W / 2 + 0.1, W / 2 - 0.1, 0.72, 1.12)]
        pb = t_panel(-W / 2 + 0.05, W / 2 - 0.05, z0, Hb - 0.08, -L / 2, -L / 2 + 0.05, holes, caps=("top", "bottom"))
        P.add(pb, M, ["TrimYellow", "Interior"], burn)
    # roof: rusted, slightly caved in
    roof = t_box(-W / 2 - 0.01, -L / 2 - 0.01, Hb - 0.08, W / 2 + 0.01, L / 2 + 0.01, Hb, 0.03)
    bmesh.ops.subdivide_edges(roof, edges=[e for e in roof.edges if abs(e.verts[0].co.y - e.verts[1].co.y) > 1], cuts=3)
    for v in roof.verts:
        if v.co.z > Hb - 0.01 and abs(v.co.y) < L / 2 - 0.3:
            v.co.z -= 0.08 * math.cos(v.co.y / L * math.pi)
    P.add(roof, None, "Rust", 0.7)
    # black stripe + bumpers + hood
    P.box(-W / 2 - 0.012, -L / 2, 0.55, W / 2 + 0.012, L / 2, 0.6, "Interior", 0.6)
    P.box(-W / 2 + 0.05, -L / 2 - 0.45, 0.2, W / 2 - 0.05, -L / 2 + 0.02, 0.62, "TrimYellow", burn)
    P.box(-W / 2, -L / 2 - 0.52, 0.18, W / 2, -L / 2 - 0.42, 0.3, "Metal", 0.6, 0.02)
    P.box(-W / 2, L / 2 - 0.02, 0.18, W / 2, L / 2 + 0.07, 0.3, "Metal", 0.6, 0.02)
    # interior floor and seat frames
    P.add(t_box(-W / 2 + 0.05, -L / 2 + 0.05, z0, W / 2 - 0.05, L / 2 - 0.05, z0 + 0.08), None, "Interior", 0.6)
    for i in range(7):
        y = -L / 2 + 0.77 + i * 0.47
        for s in (-1, 1):
            P.add(t_box(-0.18, -0.02, 0.0, 0.18, 0.02, 0.3), TR((s * 0.27, y, 0.28), (0.3, 0, 0)), "Rust", 0.5)
    # wheels: bare rims, tyres burned away
    for (x, y) in [(-W / 2 + 0.04, -L / 2 + 0.45), (W / 2 - 0.04, -L / 2 + 0.45), (-W / 2 + 0.04, L / 2 - 0.9),
                   (W / 2 - 0.04, L / 2 - 0.9)]:
        P.add(t_cyl(0.2, 0.1, 12), TR((x, y, 0.2), (0, math.pi / 2, 0)) @ TR((0, 0, -0.05)), "Rust", 0.55)
        P.add(t_cyl(0.11, 0.104, 8), TR((x, y, 0.2), (0, math.pi / 2, 0)) @ TR((0, 0, -0.052)), "Interior", 0.8)
    return P.finish(recenter=True)


def rubble(name, seed, width, height):
    rng = random.Random(seed)
    P = Piece(name, grime_prop(0.2))
    # irregular mound
    seg = 9
    r = width / 2
    bm = bmesh.new()
    rings = []
    for k, (rr, zz) in enumerate([(1.0, 0.0), (0.72, height * 0.42), (0.38, height * 0.78)]):
        ring_v = []
        for i in range(seg):
            a = 2 * math.pi * i / seg + k * 0.3
            rad = r * rr * rng.uniform(0.75, 1.05)
            ring_v.append(bm.verts.new((rad * math.cos(a), rad * math.sin(a) * 0.75, zz * rng.uniform(0.8, 1.1))))
        rings.append(ring_v)
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new([a[i], a[j], b[j], b[i]])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    P.add(bm, None, "Concrete", 0.8)
    # chunks scattered over it
    n = int(8 + width * 6)
    for i in range(n):
        s = rng.uniform(0.1, 0.32) * (0.6 + width / 4)
        a = rng.uniform(0, 2 * math.pi)
        d = math.sqrt(rng.random()) * r * 0.9
        x, y = d * math.cos(a), d * math.sin(a) * 0.75
        zsurf = height * 0.82 * (1 - (d / r) ** 1.5)
        m = rng.choice(["Concrete", "Concrete", "Concrete", "Brick", "Plaster"])
        sx, sy, sz = s * rng.uniform(0.8, 1.6), s * rng.uniform(0.6, 1.2), s * rng.uniform(0.3, 0.6)
        if m == "Brick":
            sx, sy, sz = 0.11, 0.055, 0.04
        P.add(t_box(-sx / 2, -sy / 2, -sz / 2, sx / 2, sy / 2, sz / 2, 0.015 if m != "Brick" else 0),
              TR((x, y, zsurf + sz * 0.15), (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0, 3))),
              m, rng.uniform(0.7, 1.0))
    # a slab piece with rebar
    sl, pts = jagged_slab(rng, -0.4, 0.4, -0.3, 0.3, 0.08, "x1", 4, 0.15)
    Ms = TR((rng.uniform(-0.2, 0.2) * width, 0.1, height * 0.55), (0.35, -0.4, rng.uniform(0, 3)))
    P.add(sl, Ms @ TR((0, 0, 0), (0, 0, 0), (width / 2.5, width / 2.5, 1)), "Concrete", 0.85)
    for (x, y) in pts[1:-1:2]:
        rebar_spray(P, rng, (x * width / 2.5, y * width / 2.5, 0.04), (1, 0, 0), 1, (0.15, 0.3), 0.05, M=Ms)
    for i in range(2):
        a = rng.uniform(0, 6.28)
        p = Vector((math.cos(a) * r * 0.3, math.sin(a) * r * 0.25, height * 0.7))
        rebar_spray(P, rng, p, (math.cos(a), math.sin(a), 0.8), 2, (0.25, 0.45), 0.15, droop=0.5)
    return P.finish()


def barrier():
    P = Piece("Barrier", grime_prop(0.15))
    L = 1.0
    prof = [(-0.125, 0.0), (0.125, 0.0), (0.125, 0.06), (0.07, 0.12), (0.045, 0.35), (-0.045, 0.35),
            (-0.07, 0.12), (-0.125, 0.06)]
    bm = t_prism([(-L / 2, y, z) for (y, z) in prof], (L, 0, 0))
    bmesh.ops.bevel(bm, geom=[e for e in bm.edges if abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-4],
                    offset=0.015, segments=1, affect="EDGES", profile=0.5, clamp_overlap=True)
    P.add(bm, None, "Concrete", 0.95)
    # chipped corner + stripe
    P.add(t_box(-0.25, -0.0475, 0.25, 0.25, -0.046, 0.3), TR((0, 0, 0), (0.0, 0.0, 0)) @ TR((0, -0.0, 0)),
          "TrimYellow", 0.8)
    for x in (-0.3, 0.3):
        P.add(t_bar((x, -0.13, 0.04), (x, 0.13, 0.04), 0.012, sides=4, smooth=False), None, "Rebar", 0.7)
    return P.finish()


def streetlight():
    P = Piece("Streetlight", grime_prop(0.3))
    pts = [(0, 0, 0.12), (0, 0, 1.0), (0.04, 0.0, 1.7), (0.13, 0.02, 2.35), (0.22, 0.03, 2.65)]
    P.add(t_tube(pts, [0.055, 0.05, 0.045, 0.04, 0.035], 8), None, "Metal", 0.85)
    P.add(t_cyl(0.11, 0.12, 8, r2=0.075), None, "Metal", 0.8)
    P.add(t_cyl(0.14, 0.03, 8), None, "Concrete", 0.7)
    arm = [(0.22, 0.03, 2.65), (0.3, 0.0, 2.74), (0.62, -0.03, 2.76), (0.78, -0.05, 2.7)]
    P.add(t_tube(arm, [0.035, 0.03, 0.028, 0.026], 6), None, "Metal", 0.85)
    head = t_box(-0.18, -0.08, -0.06, 0.12, 0.08, 0.04, 0.02)
    P.add(head, TR((0.85, -0.05, 2.68), (0, 0.35, 0.1)), "Metal", 0.8)
    P.add(t_quad([(-0.16, 0.06, -0.061), (0.1, 0.06, -0.061), (0.1, -0.06, -0.061), (-0.16, -0.06, -0.061)]),
          TR((0.85, -0.05, 2.68), (0, 0.35, 0.1)), "Glass", 0.9)
    # access hatch + dangling wire
    P.box(-0.012, -0.065, 0.4, 0.012, -0.045, 0.55, "Rust", 0.8)
    P.add(t_tube([(0.5, -0.03, 2.75), (0.55, -0.1, 2.3), (0.5, -0.12, 2.0)], [0.008] * 3, 4), None, "Interior", 0.8)
    return P.finish()


def barrel():
    rng = random.Random(21)
    P = Piece("Barrel", grime_prop(0.15))
    bm = t_cyl(0.25, 0.4, 14)
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1], cuts=2)
    for v in bm.verts:
        a = math.atan2(v.co.y, v.co.x)
        if 0.05 < v.co.z < 0.35 and abs(a - 0.8) < 0.5:
            v.co.x *= 0.9
            v.co.y *= 0.9
    P.add(bm, None, "Rust", 1.0)
    for z in (0.12, 0.28):
        P.add(t_cyl(0.258, 0.03, 14), TR((0, 0, z)), "Rust", 0.7)
    P.add(t_cyl(0.255, 0.02, 14), TR((0, 0, 0.395)), "Rust", 0.75)
    P.add(t_cyl(0.035, 0.012, 6), TR((0.12, 0.05, 0.4)), "Rust", 0.6)
    P.add(t_quad([(-0.08, -0.252, 0.18), (0.08, -0.252, 0.18), (0.08, -0.252, 0.26), (-0.08, -0.252, 0.26)]), None,
          "TrimYellow", 0.7)
    return P.finish()


def tire_stack():
    rng = random.Random(22)
    P = Piece("Tire_Stack", grime_prop(0.2))
    R, r = 0.2, 0.07
    for i, (x, y, z, rx, ry) in enumerate([(0, 0, r, 0, 0), (0.03, 0.02, 3 * r, 0.04, 0.0),
                                           (-0.03, 0.04, 5 * r + 0.02, 0.18, -0.1)]):
        t = t_torus(R, r, 14, 6)
        for v in t.verts:
            v.co.z *= 1.15
        P.add(t, TR((x, y, z + (0.01 if i else 0.0)), (rx, ry, rng.uniform(0, 3))), "Interior", 0.95)
    return P.finish()


def fence():
    rng = random.Random(23)
    P = Piece("Fence", grime_prop(0.2))
    Wd, Hf = 2.0, 0.9
    posts = [-Wd / 2, 0.0, Wd / 2]
    for i, x in enumerate(posts):
        lean = (0.0, 0.0) if i != 2 else (0.0, 0.08)
        P.add(t_bar((x, 0, 0), (x, lean[1], Hf), 0.025, sides=6), None, "Metal", 0.8)
        P.add(t_cyl(0.06, 0.06, 6), TR((x, 0, 0)), "Concrete", 0.7)
    def sag(x, z):
        t = (x % 1.0)
        s = math.sin(t * math.pi) * (0.06 + (0.05 if x > 0 else 0)) * sstep(1 - abs(z - Hf * 0.55) / Hf)
        return s
    def top_z(x):
        return Hf - 0.02 - (0.1 if x > 0 else 0.03) * math.sin((x % 1.0) * math.pi)
    # top rail sagging
    P.add(t_tube([(x, 0.0, top_z(x)) for x in [-1, -0.5, 0, 0.25, 0.5, 0.75, 1]], [0.016] * 7, 5), None, "Metal", 0.8)
    # chain-link: diagonal wires as thin double-sided ribbons
    sp = 0.16
    wires = []
    for dirn in (1, -1):
        for k in range(-8, 22):
            x0 = -Wd / 2 + k * sp
            pts = []
            for s in range(8):
                z = 0.05 + (Hf - 0.08) * s / 7
                x = x0 + dirn * (z - 0.05)
                if dirn < 0:
                    x = x0 - (z - 0.05) + Hf * 0.5
                pts.append((x, z))
            # clip to panel
            seg = [(x, z) for (x, z) in pts if -Wd / 2 + 0.02 <= x <= Wd / 2 - 0.02 and z <= top_z(x)]
            if len(seg) >= 2:
                wires.append(seg)
    w = 0.008
    for seg in wires:
        bm = bmesh.new()
        prev = None
        for (x, z) in seg:
            # skip a torn hole in the lower right
            y = sag(x, z)
            a = bm.verts.new((x - w, y, z))
            b = bm.verts.new((x + w, y, z))
            a2 = bm.verts.new((x - w, y + 0.002, z))
            b2 = bm.verts.new((x + w, y + 0.002, z))
            if prev and not (0.35 < x < 0.75 and z < 0.4):
                bm.faces.new([prev[0], prev[1], b, a])
                bm.faces.new([a2, b2, prev[3], prev[2]])
            prev = (a, b, a2, b2)
        P.add(bm, None, "Metal", 0.75)
    return P.finish()


def sign_down():
    P = Piece("Sign_Down", grime_prop(0.15))
    # bent pole lying on the ground, sign propped at an angle
    pole = [(-0.9, 0.1, 0.03), (-0.2, 0.05, 0.03), (0.15, 0.0, 0.08), (0.4, -0.05, 0.25)]
    P.add(t_tube(pole, [0.03] * 4, 6), None, "Metal", 0.8)
    P.add(t_box(-0.12, -0.12, 0, 0.12, 0.12, 0.08, 0.02), TR((-1.0, 0.1, 0), (0.3, 0.2, 0.4)), "Concrete", 0.7)
    oct_pts = []
    for i in range(8):
        a = math.pi / 8 + i * math.pi / 4
        oct_pts.append((0.32 * math.cos(a), 0.32 * math.sin(a), 0))
    M = TR((0.55, -0.1, 0.27), (math.radians(70), 0, math.radians(-80)))
    P.add(t_prism(oct_pts, (0, 0, 0.02)), M, "TrimRed", 0.85)
    inner = [(p[0] * 0.85, p[1] * 0.85, 0.021) for p in oct_pts]
    P.add(t_prism([(x, y, -0.002) for x, y, _ in inner], (0, 0, -0.001)), M, "Plaster", 0.95)
    P.add(t_prism([(x * 0.92, y * 0.92, -0.004) for x, y, _ in inner], (0, 0, -0.001)), M, "TrimRed", 0.85)
    # a "bar" across (no-entry style) so it reads at a distance
    P.add(t_box(-0.2, -0.05, -0.008, 0.2, 0.05, -0.005), M, "Plaster", 0.95)
    return P.finish()


def tree_dead():
    rng = random.Random(31)
    P = Piece("Tree_Dead", grime_prop(0.3))

    def branch(p, d, length, r, depth):
        pts, radii = [p], [r]
        q = Vector(p)
        dd = Vector(d).normalized()
        n = 3
        for i in range(n):
            dd = (dd + Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), rng.uniform(-0.1, 0.25)))).normalized()
            q = q + dd * length / n
            pts.append(q.copy())
            radii.append(r * (1 - 0.6 * (i + 1) / n))
        P.add(t_tube(pts, radii, 6 if depth == 0 else 5 if depth == 1 else 4, caps=False), None, "Wood",
              lambda p: 0.8 + 0.2 * noise.noise(p * 4))
        if depth < 2:
            k = 3 if depth == 0 else 2
            for j in range(k):
                idx = rng.randint(1, len(pts) - 1) if depth else [2, 3, 3][j]
                base = pts[idx]
                ang = rng.uniform(0, 2 * math.pi) + j * 2.1
                nd = Vector((math.cos(ang), math.sin(ang), rng.uniform(0.4, 1.2)))
                branch(base, nd, length * rng.uniform(0.45, 0.65), radii[idx] * 0.75, depth + 1)

    trunk = [(0, 0, 0), (0.05, 0.0, 0.5), (-0.04, 0.05, 1.0), (0.08, 0.02, 1.4)]
    P.add(t_tube(trunk, [0.12, 0.085, 0.07, 0.05], 7), None, "Wood", 0.75)
    branch((0.08, 0.02, 1.4), (0.1, 0.0, 1), 0.85, 0.05, 0)
    branch((-0.03, 0.04, 0.95), (-1, 0.3, 0.8), 0.7, 0.045, 1)
    branch((0.04, 0.0, 0.7), (0.6, -0.8, 0.7), 0.6, 0.04, 1)
    # roots / flare
    for i in range(5):
        a = i * 2 * math.pi / 5 + 0.3
        P.add(t_tube([(0, 0, 0.18), (math.cos(a) * 0.15, math.sin(a) * 0.15, 0.04), (math.cos(a) * 0.28, math.sin(a) * 0.28, -0.02)],
                     [0.06, 0.04, 0.02], 5), None, "Wood", 0.7)
    return P.finish(height=2.2)


def hydrant():
    P = Piece("Hydrant", grime_prop(0.1))
    P.add(t_cyl(0.09, 0.04, 10), None, "TrimRed", 0.8)
    P.add(t_cyl(0.065, 0.3, 10), TR((0, 0, 0.04)), "TrimRed", 0.9)
    P.add(t_cyl(0.08, 0.035, 10), TR((0, 0, 0.3)), "TrimRed", 0.85)
    P.add(t_cyl(0.07, 0.07, 10, r2=0.025), TR((0, 0, 0.335)), "TrimYellow", 0.85)
    P.add(t_cyl(0.015, 0.03, 5), TR((0, 0, 0.4)), "TrimYellow", 0.8)
    for a in (0, math.pi):
        P.add(t_cyl(0.035, 0.07, 8), TR((0, 0, 0.22), (math.pi / 2, 0, a + math.pi / 2)), "TrimRed", 0.85)
    P.add(t_cyl(0.045, 0.08, 8), TR((0, 0, 0.2), (math.pi / 2, 0, 0)), "TrimYellow", 0.8)
    return P.finish()


def dumpster():
    P = Piece("Dumpster", grime_prop(0.15))
    Lx, Wy, Hd = 0.8, 0.45, 0.5
    body = t_box(-Lx / 2, -Wy / 2, 0.06, Lx / 2, Wy / 2, Hd - 0.04, 0.015)
    for v in body.verts:
        if v.co.z > 0.2:
            v.co.y += -0.04 if v.co.y < 0 else 0.0
    P.add(body, None, "TrimTeal", lambda p: 0.7 + 0.3 * sstep((p.z - 0.05) / 0.4))
    P.add(t_box(-Lx / 2 - 0.01, -Wy / 2 - 0.06, Hd - 0.08, Lx / 2 + 0.01, Wy / 2 + 0.01, Hd - 0.04), None, "Rust", 0.8)
    # lids: one shut (tilted), one flipped open against the back
    P.add(t_box(0, -Wy / 2 - 0.05, 0, Lx / 2, Wy / 2 + 0.02, 0.025, 0.008), TR((0.0, 0, Hd - 0.04), (0.06, 0, 0)), "Rust", 0.75)
    P.add(t_box(-Lx / 2, 0, 0, 0, 0.02, 0.47, 0.008), TR((0.0, Wy / 2 + 0.02, Hd - 0.04), (-0.2, 0, 0)), "Rust", 0.75)
    for (x, y) in [(-0.32, -0.15), (0.32, -0.15), (-0.32, 0.15), (0.32, 0.15)]:
        P.add(t_cyl(0.03, 0.03, 6), TR((x - 0.015, y, 0.03), (0, math.pi / 2, 0)), "Interior", 0.8)
    P.add(t_bar((-0.3, -Wy / 2 - 0.05, 0.3), (0.3, -Wy / 2 - 0.05, 0.3), 0.015, sides=5), None, "Metal", 0.7)
    # garbage bags poking out
    for (x, y, s) in [(-0.2, 0.0, 0.14), (-0.05, 0.08, 0.12)]:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=s)
        for f in bm.faces:
            f.smooth = True
        P.add(bm, TR((x, y, Hd - 0.02), (0, 0, 0), (1, 1, 0.7)), "Interior", 0.9)
    return P.finish()


# ---------------------------------------------------------------- build everything
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = []
    # shop layouts: one per side
    brick_shop = [
        dict(win="broken", door="door", awning="TrimRed", torn=1),
        dict(win="shutter", door="boarded", flip=True),
        dict(win="boarded", door="open", burn="burned"),
        dict(win="broken", door="shutter", awning="TrimTeal", flip=True),
    ]
    conc_shop = [
        dict(win="shutter", door="door", awning="TrimYellow", door_mat="TrimTeal"),
        dict(win="broken", door="open", awning="TrimRed", torn=2, flip=True),
        dict(win="glass", door="boarded"),
        dict(win="boarded", door="door", flip=True, burn="burned"),
    ]
    office_lobby = [
        dict(win="x", door="x", office=["broken", "open", "glass"], awning=None),
        dict(win="x", door="x", office=["glass", "boarded", "broken"]),
        dict(win="x", door="x", office=["boarded", "shutter", "broken"]),
        dict(win="x", door="x", office=["broken", "open", "boarded"]),
    ]
    objs.append(shop_module("Brick_Shop", "brick", 1, brick_shop, ["TrimRed", "TrimYellow", "TrimTeal", "Trim"]))
    objs.append(shop_module("Conc_Shop", "conc", 2, conc_shop, ["TrimTeal", "TrimRed", "TrimYellow", "TrimRed"]))
    objs.append(shop_module("Office_Lobby", "office", 3, office_lobby, ["TrimTeal", "Trim", "TrimRed", "TrimTeal"]))

    objs.append(floor_module("Brick_Floor", "brick", 4,
                             ["glass", "glass", "broken", "glass", "boarded", "glass", "ac", "broken", "glass",
                              "missing", "glass", "broken"]))
    objs.append(floor_module("Brick_Floor2", "brick", 5,
                             ["broken", "burned", "missing", "boarded", "glass", "burned", "missing", "broken",
                              "boarded", "glass", "missing", "ac"]))
    objs.append(floor_module("Conc_Floor", "conc", 6,
                             ["glass", "broken", "glass", "glass", "glass", "boarded", "broken", "glass", "ac",
                              "glass", "missing", "glass"]))
    objs.append(floor_module("Conc_Floor2", "conc", 7,
                             ["missing", "burned", "boarded", "broken", "missing", "glass", "burned", "boarded",
                              "missing", "broken", "glass", "missing"]))
    objs.append(office_floor("Office_Floor", 8,
                             ["glass", "glass", "broken", "glass", "glass", "glass", "missing", "glass", "glass",
                              "broken", "glass", "glass", "glass", "boarded", "glass", "glass", "glass", "missing",
                              "glass", "broken", "glass", "glass", "glass", "glass"]))
    objs.append(office_floor("Office_Floor2", 9,
                             ["broken", "missing", "soot", "missing", "glass", "broken", "missing", "missing",
                              "glass", "soot", "broken", "boarded", "glass", "missing", "broken", "missing",
                              "soot", "glass", "missing", "broken", "glass", "missing", "boarded", "soot"]))
    objs.append(roof_module("Brick_Roof", "brick", 10))
    objs.append(roof_module("Conc_Roof", "conc", 11))
    objs.append(roof_module("Office_Roof", "office", 12))
    objs.append(brick_ruin("Brick_Ruin", 13))
    objs.append(conc_ruin("Conc_Ruin", 14, 1))
    objs.append(conc_ruin("Conc_Ruin2", 15, 2))
    objs.append(office_ruin("Office_Ruin", 16, 1))
    objs.append(office_ruin("Office_Ruin2", 17, 2))

    objs.append(car_wreck_a())
    objs.append(car_wreck_b())
    objs.append(bus_wreck())
    objs.append(rubble("Rubble_A", 41, 1.2, 0.45))
    objs.append(rubble("Rubble_B", 42, 2.0, 0.7))
    objs.append(rubble("Rubble_C", 43, 3.0, 0.95))
    objs.append(barrier())
    objs.append(streetlight())
    objs.append(barrel())
    objs.append(tire_stack())
    objs.append(fence())
    objs.append(sign_down())
    objs.append(tree_dead())
    objs.append(hydrant())
    objs.append(dumpster())
    return objs


def report(objs):
    print("REPORT name | tris | godot_min | godot_max | materials")
    for o in objs:
        me = o.data
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        # Godot: (x, z, -y)
        gmin = (min(xs), min(zs), -max(ys))
        gmax = (max(xs), max(zs), -min(ys))
        print("REPORT %-14s %5d  min(%.2f, %.2f, %.2f) max(%.2f, %.2f, %.2f)  %s" % (
            o.name, tris, *gmin, *gmax, ",".join(m.name for m in me.materials)))


def export(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "kit.glb"), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_cameras=False, export_lights=False,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False)
    print("EXPORTED", os.path.join(OUT, "kit.glb"))


# ---------------------------------------------------------------- preview render
TEXMAP = {"Concrete": ("concrete", 0.5), "Brick": ("brick", 0.6), "Plaster": ("plaster", 0.5),
          "Metal": ("metal", 0.5), "Rust": ("rust", 0.5)}


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
        if name in TEXMAP:
            tex, sc = TEXMAP[name]
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


def place_copy(src, loc, rot=0.0):
    o = bpy.data.objects.new(src.name + "_pv", src.data)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler.z = rot
    return o


def preview(objs, path, mode="lineup"):
    by = {o.name: o for o in objs}
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
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
    if os.path.exists(hdr):
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdr)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.7
    else:
        bg.inputs["Color"].default_value = (0.7, 0.72, 0.75, 1)
    # ground
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    g = bpy.context.active_object
    gm = bpy.data.materials.new("GroundPV")
    gnt = gm.node_tree
    gb = next(n for n in gnt.nodes if n.type == "BSDF_PRINCIPLED")
    ti = gnt.nodes.new("ShaderNodeTexImage")
    ti.image = bpy.data.images.load(os.path.join(TEX, "asphalt_albedo.jpg"))
    tc = gnt.nodes.new("ShaderNodeTexCoord")
    mp = gnt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.4, 0.4, 0.4)
    gnt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    gnt.links.new(mp.outputs["Vector"], ti.inputs["Vector"])
    gnt.links.new(ti.outputs["Color"], gb.inputs["Base Color"])
    gb.inputs["Roughness"].default_value = 0.95
    g.data.materials.append(gm)
    # sun
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object
    sun.data.energy = 3.2
    sun.data.angle = math.radians(3)
    sun.rotation_euler = (math.radians(50), math.radians(-12), math.radians(-35))
    for o in objs:
        o.hide_render = True
    sp = 5.0
    if mode == "lineup":
        rows = [
            ["Brick_Shop", "Brick_Floor", "Brick_Floor2", "Brick_Roof", "Brick_Ruin"],
            ["Conc_Shop", "Conc_Floor", "Conc_Floor2", "Conc_Roof", "Conc_Ruin", "Conc_Ruin2"],
            ["Office_Lobby", "Office_Floor", "Office_Floor2", "Office_Roof", "Office_Ruin", "Office_Ruin2"],
        ]
        for r, row in enumerate(rows):
            for c, n in enumerate(row):
                place_copy(by[n], (c * sp, r * 6.0, 0))
        stacks = [
            [["Brick_Shop", "Brick_Floor", "Brick_Floor2", "Brick_Roof"], ["Brick_Shop", "Brick_Floor2", "Brick_Ruin"]],
            [["Conc_Shop", "Conc_Floor", "Conc_Floor2", "Conc_Floor", "Conc_Roof"], ["Conc_Shop", "Conc_Floor2", "Conc_Ruin2"]],
            [["Office_Lobby", "Office_Floor", "Office_Floor2", "Office_Floor", "Office_Ruin"], ["Office_Lobby", "Office_Floor2", "Office_Floor", "Office_Roof"]],
        ]
        for r, pair in enumerate(stacks):
            for j, st in enumerate(pair):
                for i, n in enumerate(st):
                    place_copy(by[n], (31.0 + j * 5.0, r * 6.0, i * H))
        props = ["Car_Wreck_A", "Car_Wreck_B", "Bus_Wreck", "Rubble_A", "Rubble_B", "Rubble_C", "Barrier",
                 "Streetlight", "Barrel", "Tire_Stack", "Fence", "Sign_Down", "Tree_Dead", "Hydrant", "Dumpster"]
        x = 1.5
        for n in props:
            o = by[n]
            rot = math.pi / 2 if n in ("Bus_Wreck", "Car_Wreck_A", "Car_Wreck_B") else 0.0
            co = [(o.matrix_world.to_3x3() @ v.co) for v in o.data.vertices]
            xs = [(-c.y if rot else c.x) for c in co]
            w = max(xs) - min(xs)
            place_copy(o, (x - min(xs), -5.5, 0), rot)
            x += w + 0.7
        cam_loc, target, lens = (18.5, -21.0, 21.0), (19.5, 4.0, 0.0), 24
    elif mode == "street":
        # a little street scene to judge the look in context
        names = ["Brick_Shop", "Conc_Shop", "Office_Lobby", "Brick_Shop", "Conc_Shop"]
        ups = [["Brick_Floor", "Brick_Floor2", "Brick_Ruin"], ["Conc_Floor", "Conc_Floor2", "Conc_Floor", "Conc_Roof"],
               ["Office_Floor", "Office_Floor2", "Office_Floor", "Office_Floor2", "Office_Ruin"],
               ["Brick_Floor2", "Brick_Roof"], ["Conc_Floor2", "Conc_Ruin"]]
        for i, (s, up) in enumerate(zip(names, ups)):
            place_copy(by[s], (i * 4.0, 0, 0))
            for j, n in enumerate(up):
                place_copy(by[n], (i * 4.0, 0, (j + 1) * H))
        for i, (s, up) in enumerate(zip(["Office_Lobby", "Conc_Shop", "Brick_Shop", "Conc_Shop"],
                                         [["Office_Floor2", "Office_Ruin2"], ["Conc_Floor", "Conc_Ruin2"],
                                          ["Brick_Floor", "Brick_Floor2", "Brick_Floor", "Brick_Roof"], ["Conc_Floor2", "Conc_Roof"]])):
            place_copy(by[s], (i * 4.0 + 2, 12, 0), math.pi)
            for j, n in enumerate(up):
                place_copy(by[n], (i * 4.0 + 2, 12, (j + 1) * H), math.pi)
        for n, loc, rot in [("Car_Wreck_A", (3.5, 4.3, 0), 1.4), ("Bus_Wreck", (9.5, 6.5, 0), 1.75),
                            ("Car_Wreck_B", (5.5, 8.0, 0), 0.3), ("Rubble_B", (1.0, 3.5, 0), 0),
                            ("Rubble_C", (14.5, 4.5, 0), 0.5), ("Barrier", (7.0, 3.0, 0), 0.2),
                            ("Barrier", (8.1, 3.1, 0), -0.1), ("Streetlight", (11.5, 2.6, 0), 3.14),
                            ("Barrel", (12.6, 3.0, 0), 0), ("Tire_Stack", (0.2, 2.8, 0), 0),
                            ("Fence", (15.0, 9.0, 0), 1.2), ("Sign_Down", (4.0, 2.9, 0), 0.4),
                            ("Tree_Dead", (6.2, 9.4, 0), 0), ("Hydrant", (2.2, 2.6, 0), 0),
                            ("Dumpster", (13.6, 2.7, 0), 0.1), ("Rubble_A", (10.5, 3.2, 0), 0)]:
            place_copy(by[n], loc, rot)
        cam_loc, target, lens = (2.0, 21.0, 4.0), (8.5, 4.0, 2.6), 26
    elif mode.startswith("row:"):
        names = mode[4:].split(",")
        x = 0.0
        for n in names:
            o = by[n]
            xs = [v.co.x for v in o.data.vertices]
            w = max(xs) - min(xs)
            place_copy(o, (x - min(xs), 0, 0))
            x += w + 0.8
        xc = (x - 0.8) / 2
        span = max(x, 4)
        cam_loc, target, lens = (xc - span * 0.3, -span * 0.9, span * 0.5), (xc, 0.0, min(0.7, span * 0.1)), 35
    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = cam_loc
    cam.rotation_euler = (Vector(target) - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = lens
    cam_data.clip_end = 500
    scn.camera = cam
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    objs = build()
    report(objs)
    export(objs)
    preview_materials()
    if argv and argv[0].startswith("row:"):
        preview(objs, argv[1], argv[0])
    elif "street" in argv:
        out = argv[argv.index("street") + 1] if len(argv) > argv.index("street") + 1 else os.path.join(RENDERS, "city_kit_street.png")
        preview(objs, out, "street")
    else:
        preview(objs, os.path.join(RENDERS, "city_kit_preview.png"), "lineup")
