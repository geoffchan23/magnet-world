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
##
## Enterable buildings: about a third of the towers (more on the inner rings) are
## built from the hollow pieces in assets/city/interiors.glb (art/src/interiors_kit.py):
## an open shop door on the street side, a furnished room on every storey (shops,
## toy shop, office lobby, flats, offices, wrecked rooms), a stair up through each
## storey and, when the roof is intact, out of a bulkhead onto the roof. Their
## collision is separate wall / floor / stair / furniture boxes from interiors.json.
## Lamps glow (unshaded); a couple of warm OmniLights follow the player indoors.
##
## API for main.gd:
##   indoors_at(p: Vector3) -> bool      true when p is inside an enterable building
##                                       (any storey, or the roof bulkhead).
##   ceiling_above(p: Vector3) -> float  world height of the ceiling over p, or INF
##                                       when p is not indoors. Under the stairwell
##                                       it is the ceiling of the storey above.
##   doors: Array of {pos: Vector3 (on the pavement just outside), out: Vector3}
##   enterable: Array of building records (see tower_in()).

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

const GROUND_IN := {"Brick": "Brick_ShopIn", "Conc": "Conc_ShopIn", "Office": "Office_LobbyIn"}
const GROUND_ROOMS := {"Brick": ["Room_Grocery", "Room_Toys"], "Conc": ["Room_Toys", "Room_Grocery"], "Office": ["Room_Lobby"]}
const UPPER_ROOMS := {"Brick": ["Room_Living", "Room_Bedroom"], "Conc": ["Room_Bedroom", "Room_Living"], "Office": ["Room_Office", "Room_Meeting"]}
const MAX_ENTER_FLOORS := 6  # taller towers stay solid
const ROOF_HUT := 0.92  # height of the stair bulkhead's ceiling over the roof slab
const ROOM_CHUNK := 25.0  # furniture MultiMeshes are split into cells this big...
const ROOM_SEEN := 40.0  # ...and each is drawn only within this distance
var rng_in := RandomNumberGenerator.new()  # interior choices, so the street layout is unchanged
var in_data := {}  # interiors.json
var enterable: Array = []  # {at, yaw, storeys, roof, rooms, door}
var doors: Array = []
var in_grid := {}  # Vector2i cell -> Array of indices into enterable
var lights: Array = []  # OmniLight3D pool that follows the player indoors
var light_t := 0.0
var ring_stats := [[0, 0], [0, 0], [0, 0]]  # per ring: [towers, enterable] (for --doors)


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
	var t0 := Time.get_ticks_msec()
	rng.seed = seed_value
	rng_in.seed = seed_value * 31 + 7
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
	if "--doors" in OS.get_cmdline_user_args():
		var tris := 0
		var all_tris := 0
		for n in placed:
			var t := 0
			var pm: Mesh = pieces[n.get_slice("@", 0)]
			for i in pm.get_surface_count():
				t += pm.surface_get_array_index_len(i) / 3
			all_tris += t * placed[n].size()
			if n.begins_with("Room_") or n.ends_with("In") or n.begins_with("In_"):
				tris += t * placed[n].size()
				print("piece ", n, " x", placed[n].size(), " = ", t * placed[n].size(), " tris")
		print("interior tris %d of %d city tris" % [tris, all_tris])
	flush()
	for i in 2:
		var l := OmniLight3D.new()
		l.light_color = Color(1.0, 0.8, 0.58)
		l.light_energy = 1.4
		l.omni_range = 3.2
		l.omni_attenuation = 1.2
		l.visible = false
		add_child(l)
		lights.append(l)
	if "--doors" in OS.get_cmdline_user_args():
		var sorted := doors.duplicate()
		sorted.sort_custom(func(a, b): return a.pos.length() < b.pos.length())
		for d in sorted.filter(func(d): return d.roof).slice(0, 6) + sorted.slice(0, 4):
			print("door ", d.pos, " out ", d.out, " storeys ", d.storeys, " roof ", d.roof)
		print("rings [towers, enterable]: ", ring_stats)
		print("city: %d enterable buildings, %d storeys inside, %d collision shapes, built in %d ms" % [enterable.size(), enterable.reduce(func(a, b): return a + b.storeys, 0), body.get_child_count(), Time.get_ticks_msec() - t0])


# ---------------------------------------------------------------- kit

func load_kit() -> void:
	for path in ["res://assets/city/kit.glb", "res://assets/city/interiors.glb"]:
		load_glb(path, path.ends_with("interiors.glb"))
	var jp := "res://assets/city/interiors.json"
	if FileAccess.file_exists(jp):
		in_data = JSON.parse_string(FileAccess.get_file_as_string(jp))


func load_glb(path: String, inside: bool) -> void:
	if ResourceLoader.exists(path):
		var scene: Node3D = (load(path) as PackedScene).instantiate()
		for mi in scene.find_children("*", "MeshInstance3D", true, false):
			var m := (mi as MeshInstance3D).mesh.duplicate() as ArrayMesh
			for i in m.get_surface_count():
				m.surface_set_material(i, kit_mat(m.surface_get_material(i), inside))
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


func kit_mat(src: Material, inside := false) -> Material:
	# Swap the kit's plain materials for tiling PBR textures, matched by name.
	var name := src.resource_name if src else ""
	if name.begins_with("Glow"):
		# Lamps and screens: lit from inside, colour in the vertex colours.
		if not mats.has("glow"):
			var g := StandardMaterial3D.new()
			g.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			g.vertex_color_use_as_albedo = true
			g.disable_fog = true
			mats["glow"] = g
		return mats["glow"]
	if name.begins_with("Furn"):
		if not mats.has("furn"):
			var f := StandardMaterial3D.new()
			f.vertex_color_use_as_albedo = true
			f.roughness = 0.8
			mats["furn"] = f
		return mats["furn"]
	if inside and name.begins_with("Glass") and src is BaseMaterial3D:
		# See-through, so you can look out of the windows and peek into lit rooms.
		if not mats.has("glass_in"):
			var gl := StandardMaterial3D.new()
			gl.albedo_color = Color(0.1, 0.13, 0.15, 0.4)
			gl.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			gl.cull_mode = BaseMaterial3D.CULL_DISABLED
			gl.roughness = 0.08
			gl.metallic_specular = 0.7
			mats["glass_in"] = gl
		return mats["glass_in"]
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
	if name.begins_with("Room_"):
		# Furnished rooms only matter up close: one MultiMesh per city block, drawn
		# only near the camera.
		name = "%s@%d,%d" % [name, floori(xf.origin.x / ROOM_CHUNK), floori(xf.origin.z / ROOM_CHUNK)]
	if not placed.has(name):
		placed[name] = []
	placed[name].append(xf)


func flush() -> void:
	# One MultiMesh per kit piece.
	for name in placed:
		var list: Array = placed[name]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = pieces[name.get_slice("@", 0)]
		mm.instance_count = list.size()
		for i in list.size():
			mm.set_instance_transform(i, list[i])
		var mmi := MultiMeshInstance3D.new()
		mmi.name = name
		mmi.multimesh = mm
		if name.begins_with("Room_"):
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			mmi.visibility_range_end = ROOM_SEEN
			mmi.visibility_range_end_margin = 4.0
		elif name.begins_with("In_"):
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF  # always indoors
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
	# Which ring slots get an enterable building: about a third, more near the lot.
	var ring_i := clampi(roundi((dist - 30.0) / (ROAD + BLOCK)), 0, 2)
	var want: int = [5, 5, 5][ring_i] + rng_in.randi_range(-1, 1)
	var order := range(12)
	for i in range(11, 0, -1):
		var j := rng_in.randi_range(0, i)
		var tmp = order[i]
		order[i] = order[j]
		order[j] = tmp
	var chosen := order.slice(0, want)
	while left > 0:
		var run := mini(rng.randi_range(1, 3), left)
		var family: String = FAMILIES[rng.randi_range(0, 2)]
		var floors := rng.randi_range(0, 2) + int(tall * rng.randf_range(2, 6))
		if family == "Office":
			floors += rng.randi_range(2, 4)
		var ruined := rng.randf() < 0.6
		for r in run:
			var s: Vector2i = ring[(k + r) % 12]
			var enter: bool = ((k + r) % 12) in chosen
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
				var n_in := enterable.size()
				tower(family, at, face, floors + rng.randi_range(-1, 1), ruined, enter)
				ring_stats[ring_i][0] += 1
				ring_stats[ring_i][1] += enterable.size() - n_in
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


func tower(family: String, at: Vector3, face: float, floors: int, ruined: bool, enter := false) -> void:
	var basis := Basis(Vector3.UP, face)
	floors = maxi(floors, 0)
	# Roll every random choice first, in the same order as always, so a seed keeps its streets.
	var picks: Array = []
	for f in floors:
		picks.append([family + ("_Floor2" if rng.randf() < 0.45 else "_Floor"), rng.randi_range(0, 1)])
	var ruin := ""
	var ruin_turn := 0
	var spill := false
	var spill_x := 0.0
	var spill_pick := 0
	var spill_yaw := 0.0
	if ruined:
		var list: Array = RUINS[family]
		ruin = list[rng.randi_range(0, list.size() - 1)]
		ruin_turn = rng.randi_range(0, 3)
		if rng.randf() < 0.5:
			spill = true
			spill_x = rng.randf_range(-1.5, 1.5)
			spill_pick = rng.randi_range(0, 1)
			spill_yaw = rng.randf() * TAU
	var top := at.y + STOREY * (floors + 1)
	if enter and floors <= MAX_ENTER_FLOORS and not in_data.is_empty() and not "--no-interiors" in OS.get_cmdline_user_args():
		tower_in(family, at, face, floors, ruined)
	else:
		put(GROUND_FLOOR[family], Transform3D(basis, Vector3(at.x, at.y, at.z)))
		for f in floors:
			put(picks[f][0], Transform3D(basis.rotated(Vector3.UP, PI * picks[f][1]), Vector3(at.x, at.y + STOREY * (f + 1), at.z)))
		solid(Vector3(SLOT, top - at.y, SLOT), Transform3D(basis, at))
		if not ruined:
			put(family + "_Roof", Transform3D(basis, Vector3(at.x, top, at.z)))
			solid(Vector3(SLOT, 0.3, SLOT), Transform3D(basis, Vector3(at.x, top, at.z)))
	if ruined:
		put(ruin, Transform3D(basis.rotated(Vector3.UP, PI / 2 * ruin_turn), Vector3(at.x, top, at.z)))
		solid(Vector3(SLOT * 0.9, STOREY * 0.6, SLOT * 0.9), Transform3D(basis, Vector3(at.x, top, at.z)))
		# Chunks of the broken top lie in the street below (clear of a shop door).
		if spill:
			var sx := spill_x if not enter else -1.5
			prop(["Rubble_A", "Rubble_B"][spill_pick], at + basis * Vector3(sx, 0, 2.6 if not enter else 2.9), spill_yaw)


func tower_in(family: String, at: Vector3, face: float, floors: int, ruined: bool) -> void:
	# A building you can walk into. Storey k is turned k * 180 degrees so each stair
	# comes up through the next storey's stairwell hole (see interiors_kit.py).
	var storeys := floors + 1
	var rooms: Array = []
	for k in storeys:
		var yaw := face + PI * k
		var xf := Transform3D(Basis(Vector3.UP, yaw), at + Vector3(0, STOREY * k, 0))
		var room: String
		if k == 0:
			put_in(GROUND_IN[family], xf)
			var g: Array = GROUND_ROOMS[family]
			room = g[rng_in.randi_range(0, g.size() - 1)]
		else:
			put_in(family + "_FloorIn", xf)
			put_in("In_Slab", xf)
			var u: Array = UPPER_ROOMS[family]
			room = "Room_Wreck" if rng_in.randf() < 0.2 else u[rng_in.randi_range(0, u.size() - 1)]
		put_in(room, xf)
		rooms.append(room)
		if k < floors or not ruined:
			put_in("In_Stair", xf)
	var top := Transform3D(Basis(Vector3.UP, face + PI * storeys), at + Vector3(0, STOREY * storeys, 0))
	if not ruined:
		put_in(family + "_RoofIn", top)
	var basis := Basis(Vector3.UP, face)
	var door_x := 0.0 if family == "Office" else 0.67
	var rec := {"at": at, "yaw": face, "storeys": storeys, "roof": not ruined, "rooms": rooms, "family": family}
	enterable.append(rec)
	doors.append({"pos": at + basis * Vector3(door_x, 0, 2.3), "out": basis * Vector3(0, 0, 1), "storeys": storeys, "roof": not ruined})
	var idx := enterable.size() - 1
	for dx in [-2.0, 2.0]:
		for dz in [-2.0, 2.0]:
			var key := Vector2i(floori((at.x + dx) / 4.0), floori((at.z + dz) / 4.0))
			if not in_grid.has(key):
				in_grid[key] = []
			if not idx in in_grid[key]:
				in_grid[key].append(idx)


func put_in(name: String, xf: Transform3D) -> void:
	# An interiors piece plus its collision boxes / stair ramps from interiors.json.
	put(name, xf)
	var d: Dictionary = in_data.pieces.get(name, {})
	for b in d.get("boxes", []):
		var lo := Vector3(b[0], b[1], b[2])
		var hi := Vector3(b[3], b[4], b[5])
		var size := hi - lo
		var key := "%.3f,%.3f,%.3f" % [size.x, size.y, size.z]
		if not shape_cache.has(key):
			var bs := BoxShape3D.new()
			bs.size = size
			shape_cache[key] = bs
		var cs := CollisionShape3D.new()
		cs.shape = shape_cache[key]
		cs.transform = xf * Transform3D(Basis(), (lo + hi) / 2)
		body.add_child(cs)
	var ri := 0
	for r in d.get("ramps", []):
		# [x0, x1, y_foot, y_top, z_foot, z_top, z_end]: a wedge under stair treads / a door sill.
		var key := "ramp:%s:%d" % [name, ri]
		ri += 1
		if not shape_cache.has(key):
			var pts := PackedVector3Array()
			for x in [r[0], r[1]]:
				pts.append(Vector3(x, r[2], r[4]))
				pts.append(Vector3(x, r[3], r[5]))
				pts.append(Vector3(x, r[3], r[6]))
				pts.append(Vector3(x, r[2], r[6]))
			var cps := ConvexPolygonShape3D.new()
			cps.points = pts
			shape_cache[key] = cps
		var cs := CollisionShape3D.new()
		cs.shape = shape_cache[key]
		cs.transform = xf
		body.add_child(cs)


# ---------------------------------------------------------------- indoors queries

func building_at(p: Vector3) -> Dictionary:
	# The enterable building whose footprint holds p (ignoring height), or {}.
	var key := Vector2i(floori(p.x / 4.0), floori(p.z / 4.0))
	for i in in_grid.get(key, []):
		var b: Dictionary = enterable[i]
		var l: Vector3 = Basis(Vector3.UP, -b.yaw) * (p - b.at)
		if absf(l.x) < 1.9 and absf(l.z) < 1.9:
			return b
	return {}


func storey_local(b: Dictionary, p: Vector3, k: int) -> Vector3:
	var at: Vector3 = b.at
	return Basis(Vector3.UP, -(b.yaw + PI * k)) * (p - at - Vector3(0, STOREY * k, 0))


func in_hole(l: Vector3) -> bool:
	var h: Array = in_data.layout.hole  # [x0, z0, x1, z1] in a storey's frame
	return l.x > h[0] - 0.05 and l.x < h[2] + 0.05 and l.z > h[1] - 0.05 and l.z < h[3] + 0.05


func indoors_at(p: Vector3) -> bool:
	return ceiling_above(p) < INF


func ceiling_above(p: Vector3) -> float:
	var b := building_at(p)
	if b.is_empty():
		return INF
	var h: float = p.y - b.at.y
	var n: int = b.storeys
	if h < -0.1:
		return INF
	if h >= n * STOREY:
		# On the roof: only the stair bulkhead is indoors.
		if b.roof and h < n * STOREY + ROOF_HUT and in_hole(storey_local(b, p, n)):
			return b.at.y + n * STOREY + ROOF_HUT
		return INF
	var k := clampi(floori(h / STOREY), 0, n - 1)
	var ceil_k := k + 1
	# Under a stairwell hole (k + 1 < n, or the roof's) the ceiling is a storey higher.
	if ceil_k < n and in_hole(storey_local(b, p, ceil_k)):
		ceil_k += 1
	elif ceil_k == n and b.roof and in_hole(storey_local(b, p, ceil_k)):
		return b.at.y + n * STOREY + ROOF_HUT
	return b.at.y + ceil_k * STOREY


func _process(delta: float) -> void:
	# Warm light in the room you're in (and the one above, for the stairs).
	light_t -= delta
	if light_t > 0.0 or lights.is_empty():
		return
	light_t = 0.15
	if OS.get_cmdline_user_args().has("--stats"):
		print("stats prims ", RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME), " draws ", RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME))
	var p := Vector3.INF
	var main := get_parent()
	var pl = main.get("player") if main else null
	if pl and (pl as Node3D).visible:
		p = (pl as Node3D).global_position + Vector3(0, 0.2, 0)
	elif get_viewport().get_camera_3d():
		p = get_viewport().get_camera_3d().global_position
	var b := building_at(p) if p != Vector3.INF else {}
	var lit := 0
	if not b.is_empty():
		var k := clampi(floori((p.y - b.at.y) / STOREY), 0, b.storeys - 1)
		if p.y - b.at.y > -0.5 and p.y - b.at.y < b.storeys * STOREY:
			for s in [k, k + 1]:
				if s < b.storeys and lit < lights.size():
					var l: OmniLight3D = lights[lit]
					l.global_position = b.at + Basis(Vector3.UP, b.yaw + PI * s) * lamp_spot(b.rooms[s]) + Vector3(0, STOREY * s, 0)
					l.visible = true
					lit += 1
	for i in range(lit, lights.size()):
		lights[i].visible = false


func lamp_spot(room: String) -> Vector3:
	var best := Vector3(0, 0.9, 0)
	for s in in_data.lights.get(room, []):
		if s[1] > best.y or best == Vector3(0, 0.9, 0):
			best = Vector3(s[0], minf(s[1], 0.95), s[2])
	return best


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
