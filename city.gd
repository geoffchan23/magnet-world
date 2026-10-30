extends Node3D
## The ruined city, generated from a seed out of the Blender kit (assets/city/kit.glb).
##
## Layout: a square grid of city blocks with roads between them. The middle
## "block" is the dirt lot where you build with tiles. Each block is a raised
## pavement slab with a ring of buildings (stacks of kit storeys topped with a
## roof or a broken ruin), a junk-filled yard in the middle, and wrecks and
## barriers out on the roads. Past the last road is open wasteland.
##
## All copies of one kit piece are drawn as a single MultiMesh, so the whole city
## costs a few dozen draw calls (it has to run on an iPad).

const LOT_HALF := 15.0  # the building lot in the middle: -15..15 on both axes
const ROAD := 5.0
const BLOCK := 20.0
const RINGS := 3  # rings of blocks around the lot
const CITY_HALF := LOT_HALF + RINGS * (ROAD + BLOCK) + ROAD  # outer edge of the last road
const SLAB := 0.12  # how high the block pavement sits above the road
const STOREY := 1.25
const SLOT := 4.0  # building module footprint
const WORLD_EDGE := 150.0  # invisible walls out in the wasteland
const GROUND_LAYER := 2
const PROP_LAYER := 64  # loose things you can knock over (barrels, tyres)

const FAMILIES := ["Brick", "Conc", "Office"]
const GROUND_FLOOR := {"Brick": "Brick_Shop", "Conc": "Conc_Shop", "Office": "Office_Lobby"}
const RUINS := {"Brick": ["Brick_Ruin"], "Conc": ["Conc_Ruin", "Conc_Ruin2"], "Office": ["Office_Ruin", "Office_Ruin2"]}
# Rough sizes for stand-in boxes, used until the Blender kit exists.
const STAND_IN := {
	"Car_Wreck_A": Vector3(0.8, 0.6, 1.9), "Car_Wreck_B": Vector3(0.8, 0.7, 1.9), "Bus_Wreck": Vector3(1.05, 1.3, 4.6),
	"Rubble_A": Vector3(2.4, 0.7, 2.0), "Rubble_B": Vector3(1.6, 0.5, 1.4), "Rubble_C": Vector3(3.0, 1.0, 2.6),
	"Barrier": Vector3(1.0, 0.35, 0.25), "Streetlight": Vector3(0.2, 2.8, 0.2), "Barrel": Vector3(0.5, 0.4, 0.5),
	"Tire_Stack": Vector3(0.6, 0.45, 0.6), "Fence": Vector3(2.0, 0.9, 0.08), "Sign_Down": Vector3(0.8, 0.15, 0.5),
	"Tree_Dead": Vector3(1.2, 2.2, 1.2), "Hydrant": Vector3(0.18, 0.3, 0.18), "Dumpster": Vector3(0.8, 0.5, 0.45),
}

var rng := RandomNumberGenerator.new()
var pieces := {}  # kit piece name -> Mesh
var placed := {}  # kit piece name -> Array of Transform3D
var mats := {}
var body: StaticBody3D  # one static body holds every building/prop collision box
var shape_cache := {}
var clear_blocks: Array = []  # block corners (Vector2) left as empty plazas for stone sites


static func block_corners() -> Array:
	# Corner (x0, z0) of every city block, ring by ring outward (not the lot).
	var out := []
	for bx in block_ranges():
		for bz in block_ranges():
			if bx[0] < 0 and bx[1] > 0 and bz[0] < 0 and bz[1] > 0:
				continue
			out.append(Vector2(bx[0], bz[0]))
	return out


func build(seed_value := 2026, keep_clear: Array = []) -> void:
	rng.seed = seed_value
	clear_blocks = keep_clear
	load_kit()
	body = StaticBody3D.new()
	body.collision_layer = GROUND_LAYER
	body.collision_mask = 0
	add_child(body)
	make_ground()
	for bx in block_ranges():
		for bz in block_ranges():
			if bx[0] < 0 and bx[1] > 0 and bz[0] < 0 and bz[1] > 0:
				continue  # that's the lot
			if Vector2(bx[0], bz[0]) in clear_blocks:
				make_plaza(bx[0], bz[0])
			else:
				make_block(bx[0], bz[0])
	make_roads()
	make_lot_fence()
	make_wasteland()
	make_skyline()
	flush()


# ---------------------------------------------------------------- kit

func load_kit() -> void:
	var path := "res://assets/city/kit.glb"
	if ResourceLoader.exists(path):
		var scene: Node3D = (load(path) as PackedScene).instantiate()
		for mi in scene.find_children("*", "MeshInstance3D", true, false):
			var m := (mi as MeshInstance3D).mesh.duplicate() as ArrayMesh
			for i in m.get_surface_count():
				m.surface_set_material(i, kit_mat(m.surface_get_material(i)))
			# Keep the piece's own rotation/scale; its origin is its footprint centre.
			var b := (mi as Node3D).transform.basis
			if not b.is_equal_approx(Basis()):
				m = baked(m, b)
			pieces[(mi as Node).name] = m
		scene.free()


func baked(m: ArrayMesh, b: Basis) -> ArrayMesh:
	var out := ArrayMesh.new()
	for i in m.get_surface_count():
		var st := SurfaceTool.new()
		st.create_from(m, i)
		var arr := st.commit_to_arrays()
		var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var n: PackedVector3Array = arr[Mesh.ARRAY_NORMAL]
		for k in v.size():
			v[k] = b * v[k]
			if n.size() > k:
				n[k] = (b * n[k]).normalized()
		arr[Mesh.ARRAY_VERTEX] = v
		arr[Mesh.ARRAY_NORMAL] = n
		arr[Mesh.ARRAY_TANGENT] = null
		out.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		out.surface_set_material(i, m.surface_get_material(i))
	return out


func tex_mat(tex: String, scale: float, tint := Color.WHITE) -> StandardMaterial3D:
	var key := "%s:%s" % [tex, tint.to_html()]
	if mats.has(key):
		return mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_texture = load("res://assets/textures/%s_albedo.jpg" % tex)
	m.albedo_color = tint
	m.normal_enabled = true
	m.normal_texture = load("res://assets/textures/%s_normal.jpg" % tex)
	m.roughness_texture = load("res://assets/textures/%s_arm.jpg" % tex)
	m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	m.metallic_texture = m.roughness_texture
	m.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE
	m.ao_enabled = true
	m.ao_texture = m.roughness_texture
	m.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE * scale
	m.vertex_color_use_as_albedo = true
	mats[key] = m
	return m


func kit_mat(src: Material) -> Material:
	# Swap the kit's plain materials for tiling PBR textures, matched by name.
	var name := src.resource_name if src else ""
	var base := (src as BaseMaterial3D).albedo_color if src is BaseMaterial3D else Color.WHITE
	# The kit's base colours are tints for the textures (Trim ones are real colours).
	if name.begins_with("Concrete"):
		return tex_mat("concrete", 0.5, base)
	if name.begins_with("Brick"):
		return tex_mat("brick", 0.6, base)
	if name.begins_with("Plaster") or name.begins_with("Trim"):
		return tex_mat("plaster", 0.5, base)
	if name.begins_with("Rust"):
		return tex_mat("rust", 0.7, base)
	if src is BaseMaterial3D:
		(src as BaseMaterial3D).vertex_color_use_as_albedo = true
	return src


func piece(name: String) -> Mesh:
	if not pieces.has(name):
		pieces[name] = stand_in(name)
	return pieces[name]


func stand_in(name: String) -> Mesh:
	var size: Vector3 = STAND_IN.get(name, Vector3(SLOT, STOREY, SLOT))
	if name.ends_with("Roof"):
		size = Vector3(SLOT, 0.4, SLOT)
	elif name.contains("Ruin"):
		size = Vector3(SLOT * 0.8, STOREY * 1.3, SLOT * 0.6)
	var box := BoxMesh.new()
	box.size = size
	var m := StandardMaterial3D.new()
	m.albedo_color = Color("9c5a43") if name.begins_with("Brick") else Color("8b8f94") if name.begins_with("Office") else Color("b9ae9b")
	box.material = m
	# Kit pieces sit on their origin; boxes are centred, so lift them.
	var am := ArrayMesh.new()
	var arr := box.get_mesh_arrays()
	var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
	for k in v.size():
		v[k].y += size.y / 2
	arr[Mesh.ARRAY_VERTEX] = v
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	am.surface_set_material(0, m)
	return am


func put(name: String, xf: Transform3D) -> void:
	piece(name)
	if not placed.has(name):
		placed[name] = []
	placed[name].append(xf)


func flush() -> void:
	# One MultiMesh per kit piece.
	for name in placed:
		var list: Array = placed[name]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = pieces[name]
		mm.instance_count = list.size()
		for i in list.size():
			mm.set_instance_transform(i, list[i])
		var mmi := MultiMeshInstance3D.new()
		mmi.name = name
		mmi.multimesh = mm
		add_child(mmi)
	placed.clear()


func solid(size: Vector3, xf: Transform3D) -> void:
	# A collision box (size measured from its base) in the shared static body.
	var cs := CollisionShape3D.new()
	var key := "%.2f,%.2f,%.2f" % [size.x, size.y, size.z]
	if not shape_cache.has(key):
		var b := BoxShape3D.new()
		b.size = size
		shape_cache[key] = b
	cs.shape = shape_cache[key]
	cs.transform = xf * Transform3D(Basis(), Vector3(0, size.y / 2, 0))
	body.add_child(cs)


func prop(name: String, at: Vector3, yaw: float, collide := true) -> void:
	var xf := Transform3D(Basis(Vector3.UP, yaw), at)
	put(name, xf)
	if collide:
		var aabb := piece(name).get_aabb()
		var cs := CollisionShape3D.new()
		var b := BoxShape3D.new()
		b.size = aabb.size
		cs.shape = b
		cs.transform = xf * Transform3D(Basis(), aabb.get_center())
		body.add_child(cs)


func loose(name: String, at: Vector3, yaw: float) -> void:
	# Something you can knock flying with the buggy.
	var rb := RigidBody3D.new()
	rb.collision_layer = PROP_LAYER
	rb.collision_mask = 1 | GROUND_LAYER | 4 | 8 | 32 | PROP_LAYER
	rb.mass = 0.6 if name == "Barrel" else 1.0
	rb.can_sleep = true
	rb.sleeping = true
	var mi := MeshInstance3D.new()
	mi.mesh = piece(name)
	rb.add_child(mi)
	var aabb := mi.mesh.get_aabb()
	var cs := CollisionShape3D.new()
	var shape_key := "loose:" + name
	if not shape_cache.has(shape_key):
		var b := BoxShape3D.new()
		b.size = aabb.size * 0.95
		shape_cache[shape_key] = b
	cs.shape = shape_cache[shape_key]
	cs.position = aabb.get_center()
	rb.add_child(cs)
	add_child(rb)
	rb.global_transform = Transform3D(Basis(Vector3.UP, yaw), at + Vector3(0, 0.01, 0))


# ---------------------------------------------------------------- layout

static func block_ranges() -> Array:
	# [start, end] of every block (and the lot) along one axis.
	var out := [[-LOT_HALF, LOT_HALF]]
	for k in RINGS:
		var a := LOT_HALF + ROAD + k * (ROAD + BLOCK)
		out.append([a, a + BLOCK])
		out.append([-a - BLOCK, -a])
	return out


static func road_centres() -> Array:
	var out := []
	for k in RINGS + 1:
		var c := LOT_HALF + ROAD / 2 + k * (ROAD + BLOCK)
		out.append(c)
		out.append(-c)
	return out


func make_ground() -> void:
	var noise := NoiseTexture2D.new()
	noise.width = 256
	noise.height = 256
	noise.seamless = true
	var fnl := FastNoiseLite.new()
	fnl.frequency = 0.02
	fnl.fractal_octaves = 4
	noise.noise = fnl
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/city_ground.gdshader")
	mat.set_shader_parameter("asphalt_tex", load("res://assets/textures/asphalt_albedo.jpg"))
	mat.set_shader_parameter("asphalt_nrm", load("res://assets/textures/asphalt_normal.jpg"))
	mat.set_shader_parameter("dirt_tex", load("res://assets/textures/dirt_albedo.jpg"))
	mat.set_shader_parameter("dirt_nrm", load("res://assets/textures/dirt_normal.jpg"))
	mat.set_shader_parameter("noise_tex", noise)
	mat.set_shader_parameter("lot_half", LOT_HALF)
	mat.set_shader_parameter("road", ROAD)
	mat.set_shader_parameter("block", BLOCK)
	mat.set_shader_parameter("city_half", CITY_HALF)
	mat.set_shader_parameter("grid_radius", get_parent().BUILD_R)
	var plane := PlaneMesh.new()
	plane.size = Vector2(1200, 1200)
	plane.subdivide_width = 24
	plane.subdivide_depth = 24
	var mi := MeshInstance3D.new()
	mi.mesh = plane
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	var floor_shape := CollisionShape3D.new()
	floor_shape.shape = WorldBoundaryShape3D.new()
	body.add_child(floor_shape)
	# Invisible walls far out in the wasteland so nobody drives off forever.
	for i in 4:
		var yaw := i * PI / 2
		var dir := Vector3(sin(yaw), 0, cos(yaw))
		solid(Vector3(WORLD_EDGE * 2, 20, 1), Transform3D(Basis(Vector3.UP, yaw), dir * WORLD_EDGE))


func make_plaza(x0: float, z0: float) -> void:
	# An empty paved block: an Infinity Stone site gets built here (stones.gd).
	var slab := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(BLOCK, SLAB, BLOCK)
	slab.mesh = box
	slab.material_override = tex_mat("pavement", 0.35)
	slab.position = Vector3(x0 + BLOCK / 2, SLAB / 2, z0 + BLOCK / 2)
	add_child(slab)
	solid(Vector3(BLOCK, SLAB, BLOCK), Transform3D(Basis(), Vector3(x0 + BLOCK / 2, 0, z0 + BLOCK / 2)))


func make_block(x0: float, z0: float) -> void:
	# Raised pavement slab with a kerb.
	var slab := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(BLOCK, SLAB, BLOCK)
	slab.mesh = box
	slab.material_override = tex_mat("pavement", 0.35)
	slab.position = Vector3(x0 + BLOCK / 2, SLAB / 2, z0 + BLOCK / 2)
	add_child(slab)
	solid(Vector3(BLOCK, SLAB, BLOCK), Transform3D(Basis(), Vector3(x0 + BLOCK / 2, 0, z0 + BLOCK / 2)))

	# 4x4 grid of building slots, set back from the kerb by a pavement ring.
	var inset := (BLOCK - 4 * SLOT) / 2
	var ring: Array = []  # perimeter slots, in walking order
	for i in 4:
		ring.append(Vector2i(i, 0))
	for j in range(1, 4):
		ring.append(Vector2i(3, j))
	for i in range(2, -1, -1):
		ring.append(Vector2i(i, 3))
	for j in range(2, 0, -1):
		ring.append(Vector2i(0, j))
	# Buildings further from the middle are taller, so the skyline rises around the lot.
	var dist := maxf(absf(x0 + BLOCK / 2), absf(z0 + BLOCK / 2))
	var tall := clampf((dist - 30.0) / 50.0, 0.0, 1.0)
	var k := rng.randi_range(0, 11)
	var left := 12
	while left > 0:
		var run := mini(rng.randi_range(1, 3), left)
		var family: String = FAMILIES[rng.randi_range(0, 2)]
		var floors := rng.randi_range(0, 2) + int(tall * rng.randf_range(2, 6))
		if family == "Office":
			floors += rng.randi_range(2, 4)
		var ruined := rng.randf() < 0.6
		for r in run:
			var s: Vector2i = ring[(k + r) % 12]
			var at := Vector3(x0 + inset + SLOT * (s.x + 0.5), SLAB, z0 + inset + SLOT * (s.y + 0.5))
			# Buildings face the street they're on.
			var face := 0.0
			if s.y == 0:
				face = PI
			elif s.y == 3:
				face = 0.0
			elif s.x == 0:
				face = -PI / 2
			else:
				face = PI / 2
			if rng.randf() < 0.1:
				collapsed(at)
			else:
				tower(family, at, face, floors + rng.randi_range(-1, 1), ruined)
		k += run
		left -= run
	yard(Vector3(x0 + BLOCK / 2, SLAB, z0 + BLOCK / 2))
	# Street lights along the kerb.
	for side in 4:
		var yaw := side * PI / 2
		var out := Vector3(sin(yaw), 0, cos(yaw))
		var along := Vector3(out.z, 0, -out.x)
		for t: float in [-6.0, 6.0]:
			if rng.randf() < 0.75:
				var p := Vector3(x0 + BLOCK / 2, SLAB, z0 + BLOCK / 2) + out * (BLOCK / 2 - 0.4) + along * t
				prop("Streetlight", p, yaw + rng.randf_range(-0.2, 0.2))
		if rng.randf() < 0.4:
			prop("Hydrant", Vector3(x0 + BLOCK / 2, SLAB, z0 + BLOCK / 2) + out * (BLOCK / 2 - 0.5) + along * rng.randf_range(-8, 8), rng.randf() * TAU)


func tower(family: String, at: Vector3, face: float, floors: int, ruined: bool) -> void:
	var basis := Basis(Vector3.UP, face)
	var y := at.y
	put(GROUND_FLOOR[family], Transform3D(basis, Vector3(at.x, y, at.z)))
	y += STOREY
	for f in maxi(floors, 0):
		var pick := family + ("_Floor2" if rng.randf() < 0.45 else "_Floor")
		put(pick, Transform3D(basis.rotated(Vector3.UP, PI * rng.randi_range(0, 1)), Vector3(at.x, y, at.z)))
		y += STOREY
	solid(Vector3(SLOT, y - at.y, SLOT), Transform3D(basis, at))
	if ruined:
		var list: Array = RUINS[family]
		put(list[rng.randi_range(0, list.size() - 1)], Transform3D(basis.rotated(Vector3.UP, PI / 2 * rng.randi_range(0, 3)), Vector3(at.x, y, at.z)))
		solid(Vector3(SLOT * 0.9, STOREY * 0.6, SLOT * 0.9), Transform3D(basis, Vector3(at.x, y, at.z)))
		# Chunks of the broken top lie in the street below.
		if rng.randf() < 0.5:
			var spill := at + basis * Vector3(rng.randf_range(-1.5, 1.5), 0, 2.6)
			prop(["Rubble_A", "Rubble_B"][rng.randi_range(0, 1)], spill, rng.randf() * TAU)
	else:
		put(family + "_Roof", Transform3D(basis, Vector3(at.x, y, at.z)))
		solid(Vector3(SLOT, 0.3, SLOT), Transform3D(basis, Vector3(at.x, y, at.z)))


func collapsed(at: Vector3) -> void:
	# A building that has already fallen down: just a big rubble heap.
	prop("Rubble_C", at, rng.randf() * TAU)
	if rng.randf() < 0.5:
		prop("Rubble_A", at + Vector3(rng.randf_range(-1, 1), 0, rng.randf_range(-1, 1)), rng.randf() * TAU)


func yard(centre: Vector3) -> void:
	# The middle of each block: back-lot junk.
	for i in rng.randi_range(2, 5):
		var p := centre + Vector3(rng.randf_range(-3.5, 3.5), 0, rng.randf_range(-3.5, 3.5))
		match rng.randi_range(0, 5):
			0:
				prop("Dumpster", p, rng.randf() * TAU)
			1:
				prop("Tree_Dead", p, rng.randf() * TAU)
			2:
				prop("Rubble_B", p, rng.randf() * TAU)
			3:
				loose("Barrel", p, rng.randf() * TAU)
			4:
				prop("Fence", p, rng.randi_range(0, 3) * PI / 2)
			5:
				loose("Tire_Stack", p, rng.randf() * TAU)


func make_roads() -> void:
	# Wrecks and junk along every stretch of road between two crossings, leaving
	# the middle of the road clear enough to drive.
	var centres := road_centres()
	for c in centres:
		for b in block_ranges():
			for along_x in [true, false]:
				var a0: float = b[0]
				var a1: float = b[1]
				var n := rng.randi_range(0, 3)
				for i in n:
					var t := rng.randf_range(a0 + 1.5, a1 - 1.5)
					var lane := (ROAD / 2 - 0.7) * (1.0 if rng.randf() < 0.5 else -1.0)
					var p: Vector3 = Vector3(t, 0, c + lane) if along_x else Vector3(c + lane, 0, t)
					var yaw: float = (PI / 2 if along_x else 0.0) + rng.randf_range(-0.5, 0.5) + (PI if rng.randf() < 0.5 else 0.0)
					if absf(p.x) < LOT_HALF + ROAD and absf(p.z) < LOT_HALF + ROAD:
						continue  # keep the roads around the lot clear
					var r := rng.randf()
					if r < 0.45:
						prop("Car_Wreck_A" if rng.randf() < 0.6 else "Car_Wreck_B", p, yaw)
					elif r < 0.55:
						prop("Bus_Wreck", p, yaw * 0.3 + (PI / 2 if along_x else 0.0))
					elif r < 0.75:
						for j in 3:
							prop("Barrier", p + Vector3(j * 1.05, 0, 0).rotated(Vector3.UP, yaw), yaw)
					elif r < 0.85:
						prop("Sign_Down", p, rng.randf() * TAU, false)
					else:
						loose("Barrel", p, 0.0)
						loose("Barrel", p + Vector3(0.55, 0, 0.2), 0.0)
						loose("Tire_Stack", p + Vector3(-0.3, 0, 0.6), 0.0)


func make_lot_fence() -> void:
	# Chain-link fence around the building lot, with a wide gap in each side to drive in.
	for side in 4:
		var yaw := side * PI / 2
		var out := Vector3(sin(yaw), 0, cos(yaw))
		var along := Vector3(out.z, 0, -out.x)
		for t: float in [-13.0, -11.0, -9.0, -7.0, -5.0, 5.0, 7.0, 9.0, 11.0, 13.0]:
			if rng.randf() < 0.85:
				var lean := Basis(along, rng.randf_range(-0.12, 0.05))
				var p := out * (LOT_HALF - 0.6) + along * t
				put("Fence", Transform3D(lean * Basis(Vector3.UP, yaw), p))
				solid(Vector3(2.0, 0.9, 0.08), Transform3D(Basis(Vector3.UP, yaw), p))
	for i in 6:
		var a := rng.randf() * TAU
		var r := rng.randf_range(get_parent().BUILD_R + 0.6, LOT_HALF - 1.2)
		loose(["Barrel", "Tire_Stack"][i % 2], Vector3(cos(a) * r, 0, sin(a) * r), rng.randf() * TAU)


func make_wasteland() -> void:
	# Past the last road: open ground with the odd wreck, heap and dead tree.
	for i in 140:
		var a := rng.randf() * TAU
		var r := rng.randf_range(CITY_HALF + 4.0, WORLD_EDGE + 40.0)
		var p := Vector3(cos(a) * r, 0, sin(a) * r)
		if absf(p.x) < CITY_HALF + 3.0 and absf(p.z) < CITY_HALF + 3.0:
			continue
		var pick: String = ["Rubble_C", "Rubble_A", "Tree_Dead", "Tree_Dead", "Car_Wreck_A", "Car_Wreck_B", "Bus_Wreck", "Rubble_B"][rng.randi_range(0, 7)]
		prop(pick, p, rng.randf() * TAU, r < WORLD_EDGE)


func make_skyline() -> void:
	# Far-off ruined towers, softened by the haze, so the city feels endless.
	for i in 36:
		var a := TAU * i / 36.0 + rng.randf_range(-0.05, 0.05)
		var r := rng.randf_range(210.0, 300.0)
		var family: String = ["Office", "Conc", "Office"][rng.randi_range(0, 2)]
		var s := rng.randf_range(2.2, 3.4)
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * s)
		var p := Vector3(cos(a) * r, 0, sin(a) * r)
		var floors := rng.randi_range(4, 12)
		put(GROUND_FLOOR[family], Transform3D(basis, p))
		for f in floors:
			put(family + "_Floor", Transform3D(basis, p + Vector3(0, STOREY * s * (f + 1), 0)))
		var list: Array = RUINS[family]
		put(list[rng.randi_range(0, list.size() - 1)], Transform3D(basis, p + Vector3(0, STOREY * s * (floors + 1), 0)))
