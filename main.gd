extends Node3D
## Magnet World: build with magnetic tiles, then hop in and explore.
##
## Every tile is a flat polygon. Its edges are "magnets": hover an edge and the
## new tile hinges off it. The hinge angle is chosen for you (and R flips through
## the other options); if the new tile's free corners would land on an existing
## corner, that angle wins - that's the magnetic "click" that closes boxes and
## pyramids.

const COLORS := [
	Color("ff4d4d"), Color("ff9a2e"), Color("ffd93b"), Color("41d36b"),
	Color("2ea8ff"), Color("8a5cff"), Color("ff6fc0"),
]
const SHAPES := ["square", "triangle", "tall", "big"]
const SHAPE_LABELS := {"square": "Square", "triangle": "Triangle", "tall": "Tall\nTriangle", "big": "Big\nSquare"}
const SAVE_PATH := "user://world.json"
const T := 0.05  # tile (frame) thickness
const SNAP_EPS := 0.07  # how close corners must get to "click" together
const H := 0.8660254  # height of a unit equilateral triangle

var tiles: Array = []  # {id, shape, color, xform, verts (world), node}
var next_id := 1
var undo_stack: Array = []

var cur_shape := "square"
var cur_color := 4
var erase_mode := false
var play_mode := false
var ground_rot := 0

var cam: Camera3D
var cam_target := Vector3(0.5, 0.4, 0.5)
var cam_yaw := 0.7
var cam_pitch := 0.6
var cam_dist := 7.0

var ghost: MeshInstance3D
var ghost_mat: StandardMaterial3D
var erase_mat: StandardMaterial3D
var hover_key := ""
var hover_ground := false
var hover_tile = null
var candidates: Array = []
var cand_index := 0

var player: CharacterBody3D
var sfx: AudioStreamPlayer
var click_snd: AudioStreamWAV
var pop_snd: AudioStreamWAV

var orbiting := false
var right_press_pos := Vector2.ZERO
var right_moved := false

var mesh_cache := {}
var mat_cache := {}
var hint_label: Label
var status_label: Label
var play_button: Button
var erase_button: Button
var undo_button: Button
var shape_buttons := {}
var color_buttons: Array = []

var demo := false
var shot_path := ""
var frame_count := 0
var cam_override := PackedFloat64Array()


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--demo":
			demo = true
		elif a.begins_with("--shot="):
			shot_path = a.substr(7)
		elif a.begins_with("--cam="):
			cam_override = a.substr(6).split_floats(",")
	setup_world()
	setup_ghost()
	setup_audio()
	setup_player()
	setup_ui()
	if demo:
		build_demo()
	else:
		load_world()
	if cam_override.size() == 6:
		cam_yaw = cam_override[0]
		cam_pitch = cam_override[1]
		cam_dist = cam_override[2]
		cam_target = Vector3(cam_override[3], cam_override[4], cam_override[5])
	if "--play" in OS.get_cmdline_user_args():
		set_play(true)
	refresh_ui()


# ---------------------------------------------------------------- world setup

func setup_world() -> void:
	var env := Environment.new()
	var sky_mat := PanoramaSkyMaterial.new()
	sky_mat.panorama = load("res://assets/textures/sky.hdr")
	sky_mat.energy_multiplier = 1.1
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.8
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.0
	env.glow_enabled = true
	env.glow_intensity = 0.4
	env.glow_hdr_threshold = 1.2
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color("bcd8f5")
	env.fog_depth_begin = 40.0
	env.fog_depth_end = 260.0
	env.fog_density = 0.35
	env.fog_sky_affect = 0.0
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.2
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -30, 0)
	sun.light_energy = 1.6
	sun.light_color = Color("fff3e0")
	sun.shadow_enabled = true
	sun.shadow_blur = 1.5
	sun.directional_shadow_max_distance = 40.0
	add_child(sun)

	setup_islands()
	setup_cloud_sea()
	scatter_grass.call_deferred()

	cam = Camera3D.new()
	cam.fov = 55
	cam.far = 600
	add_child(cam)


func setup_islands() -> void:
	var grass := ShaderMaterial.new()
	grass.shader = load("res://shaders/island_top.gdshader")
	grass.set_shader_parameter("albedo_tex", load("res://assets/textures/grass_albedo.jpg"))
	grass.set_shader_parameter("normal_tex", load("res://assets/textures/grass_normal.jpg"))
	var grass_decor := grass.duplicate()
	grass_decor.set_shader_parameter("grid_strength", 0.0)
	var rock := ORMMaterial3D.new()
	rock.albedo_texture = load("res://assets/textures/rock_albedo.jpg")
	rock.normal_enabled = true
	rock.normal_texture = load("res://assets/textures/rock_normal.jpg")
	rock.orm_texture = load("res://assets/textures/rock_arm.jpg")
	rock.uv1_triplanar = true
	rock.uv1_scale = Vector3(0.35, 0.35, 0.35)
	rock.vertex_color_use_as_albedo = true
	var bark := rock.duplicate()
	bark.albedo_color = Color("8a6648")
	bark.uv1_scale = Vector3(1.2, 1.2, 1.2)
	var leaves := StandardMaterial3D.new()
	leaves.albedo_color = Color("5f9e3a")
	leaves.vertex_color_use_as_albedo = true
	leaves.roughness = 0.75
	leaves.backlight_enabled = true
	leaves.backlight = Color("3d6b1f")
	var mats := {"Grass": grass, "Rock": rock, "Bark": bark, "Leaves": leaves}

	for path in ["res://assets/islands/main.glb", "res://assets/islands/decor.glb"]:
		var scene: Node3D = (load(path) as PackedScene).instantiate()
		add_child(scene)
		for mi in scene.find_children("*", "MeshInstance3D", true, false):
			var m: Mesh = (mi as MeshInstance3D).mesh
			for i in m.get_surface_count():
				var src := m.surface_get_material(i)
				var key := src.resource_name if src else ""
				if mats.has(key):
					var use: Material = mats[key]
					if key == "Grass" and path.ends_with("decor.glb"):
						use = grass_decor
					(mi as MeshInstance3D).set_surface_override_material(i, use)
			# Islands are solid ground (you can walk off the edge though!).
			if (mi as Node).name.contains("Island") or (mi as Node).name.begins_with("Sat"):
				(mi as MeshInstance3D).create_trimesh_collision()
				for body in (mi as Node).find_children("*", "StaticBody3D", true, false):
					(body as StaticBody3D).collision_layer = 2
					(body as StaticBody3D).collision_mask = 0


func grass_tuft_mesh() -> ArrayMesh:
	# A handful of tapered blades fanned around the origin.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for b in 6:
		var a := rng.randf() * TAU
		var dir := Vector3(cos(a), 0, sin(a))
		var side := Vector3(-dir.z, 0, dir.x) * 0.018
		var base := dir * rng.randf_range(0.0, 0.05)
		var h := rng.randf_range(0.14, 0.28)
		var lean := dir * rng.randf_range(0.03, 0.09)
		var mid := base + lean * 0.4 + Vector3(0, h * 0.55, 0)
		var top := base + lean + Vector3(0, h, 0)
		var quad := [
			[base - side, 0.0], [base + side, 0.0], [mid + side * 0.6, 0.55],
			[base - side, 0.0], [mid + side * 0.6, 0.55], [mid - side * 0.6, 0.55],
			[mid - side * 0.6, 0.55], [mid + side * 0.6, 0.55], [top, 1.0],
		]
		for v in quad:
			st.set_normal(Vector3.UP)
			st.set_uv(Vector2(0, v[1]))
			st.add_vertex(v[0])
	return st.commit()


func scatter_grass() -> void:
	# Wait for the island collision to exist, then drop tufts onto it.
	await get_tree().physics_frame
	await get_tree().physics_frame
	var space := get_world_3d().direct_space_state
	var rng := RandomNumberGenerator.new()
	rng.seed = 42
	var xforms: Array = []
	var colors: Array = []
	for i in 9000:
		if xforms.size() >= 3200:
			break
		var a := rng.randf() * TAU
		var r := sqrt(rng.randf()) * 8.8
		if r < 5.7 and rng.randf() > 0.04:
			continue  # keep the build area mostly clear
		var p := Vector3(cos(a) * r, 2.0, sin(a) * r)
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(p, p + Vector3.DOWN * 4.0, 2))
		if hit.is_empty() or (hit.normal as Vector3).y < 0.6:
			continue
		var s := rng.randf_range(0.7, 1.4)
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.8, 1.3), s))
		xforms.append(Transform3D(basis, hit.position))
		var g := rng.randf_range(0.85, 1.15)
		colors.append(Color(g * rng.randf_range(0.9, 1.1), g, g * 0.9))
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = grass_tuft_mesh()
	mm.instance_count = xforms.size()
	for i in xforms.size():
		mm.set_instance_transform(i, xforms[i])
		mm.set_instance_color(i, colors[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/grass.gdshader")
	mmi.material_override = mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mmi)


func setup_cloud_sea() -> void:
	var noise := NoiseTexture2D.new()
	noise.width = 512
	noise.height = 512
	noise.seamless = true
	var fnl := FastNoiseLite.new()
	fnl.frequency = 0.008
	fnl.fractal_octaves = 5
	noise.noise = fnl
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/cloud_sea.gdshader")
	mat.set_shader_parameter("noise_tex", noise)
	for layer in [[-16.0, 0.0], [-22.0, 0.37]]:
		var mi := MeshInstance3D.new()
		var plane := PlaneMesh.new()
		plane.size = Vector2(600, 600)
		mi.mesh = plane
		mi.material_override = mat
		mi.position = Vector3(layer[1] * 100.0, layer[0], 0)
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)

func setup_ghost() -> void:
	ghost_mat = StandardMaterial3D.new()
	ghost_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ghost_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ghost_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	erase_mat = ghost_mat.duplicate()
	erase_mat.albedo_color = Color(1, 0.1, 0.1, 0.55)
	erase_mat.no_depth_test = true
	ghost = MeshInstance3D.new()
	ghost.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ghost.visible = false
	add_child(ghost)


func setup_player() -> void:
	player = CharacterBody3D.new()
	player.set_script(preload("res://player.gd"))
	player.main = self
	player.collision_layer = 4
	player.collision_mask = 1 | 2
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.13
	cap.height = 0.5
	cs.shape = cap
	cs.position.y = 0.25
	player.add_child(cs)

	var visual := Node3D.new()
	visual.name = "Visual"
	player.add_child(visual)
	var body := MeshInstance3D.new()
	var cm := CapsuleMesh.new()
	cm.radius = 0.13
	cm.height = 0.5
	body.mesh = cm
	body.position.y = 0.25
	var bm := StandardMaterial3D.new()
	bm.albedo_color = Color("ff8a3d")
	bm.roughness = 0.5
	body.material_override = bm
	visual.add_child(body)
	var white := StandardMaterial3D.new()
	white.albedo_color = Color.WHITE
	var black := StandardMaterial3D.new()
	black.albedo_color = Color("1b1b1b")
	for sx in [-0.055, 0.055]:
		var eye := MeshInstance3D.new()
		var es := SphereMesh.new()
		es.radius = 0.04
		es.height = 0.08
		eye.mesh = es
		eye.material_override = white
		eye.position = Vector3(sx, 0.38, -0.11)
		visual.add_child(eye)
		var pupil := MeshInstance3D.new()
		var ps := SphereMesh.new()
		ps.radius = 0.02
		ps.height = 0.04
		pupil.mesh = ps
		pupil.material_override = black
		pupil.position = Vector3(sx, 0.38, -0.145)
		visual.add_child(pupil)
	add_child(player)
	set_player_active(false)


func set_player_active(on: bool) -> void:
	player.visible = on
	player.process_mode = Node.PROCESS_MODE_INHERIT if on else Node.PROCESS_MODE_DISABLED
	player.collision_layer = 4 if on else 0


# ---------------------------------------------------------------- tile shapes

static func shape_verts(shape: String) -> PackedVector3Array:
	# All shapes lie flat in local XZ with their centroid at the origin.
	match shape:
		"triangle":
			return PackedVector3Array([Vector3(-0.5, 0, H / 3), Vector3(0.5, 0, H / 3), Vector3(0, 0, -2 * H / 3)])
		"tall":
			var h := 1.4
			return PackedVector3Array([Vector3(-0.5, 0, h / 3), Vector3(0.5, 0, h / 3), Vector3(0, 0, -2 * h / 3)])
		"big":
			return PackedVector3Array([Vector3(-1, 0, -1), Vector3(1, 0, -1), Vector3(1, 0, 1), Vector3(-1, 0, 1)])
	return PackedVector3Array([Vector3(-0.5, 0, -0.5), Vector3(0.5, 0, -0.5), Vector3(0.5, 0, 0.5), Vector3(-0.5, 0, 0.5)])


static func centroid(v: PackedVector3Array) -> Vector3:
	var c := Vector3.ZERO
	for p in v:
		c += p
	return c / v.size()


func panel_mesh(shape: String) -> ArrayMesh:
	if mesh_cache.has(shape):
		return mesh_cache[shape]
	var v := shape_verts(shape)
	var n := v.size()
	var up := Vector3(0, T / 2, 0)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(1, n - 1):
		for p in [v[0], v[i], v[i + 1]]:
			st.set_normal(Vector3.UP)
			st.add_vertex(p + up)
		for p in [v[0], v[i + 1], v[i]]:
			st.set_normal(Vector3.DOWN)
			st.add_vertex(p - up)
	var c := centroid(v)
	for i in n:
		var a := v[i]
		var b := v[(i + 1) % n]
		var x := (b - a).normalized()
		var out := (a + b) / 2 - c
		out = (out - x * out.dot(x)).normalized()
		for p in [a + up, b + up, b - up, a + up, b - up, a - up]:
			st.set_normal(out)
			st.add_vertex(p)
	var m := st.commit()
	mesh_cache[shape] = m
	return m


func panel_mat(ci: int) -> ShaderMaterial:
	var key := "p%d" % ci
	if not mat_cache.has(key):
		var m := ShaderMaterial.new()
		m.shader = load("res://shaders/tile_panel.gdshader")
		m.set_shader_parameter("tint", COLORS[ci])
		mat_cache[key] = m
	return mat_cache[key]


func frame_mat(ci: int) -> StandardMaterial3D:
	var key := "f%d" % ci
	if not mat_cache.has(key):
		var m := StandardMaterial3D.new()
		m.albedo_color = (COLORS[ci] as Color).darkened(0.05)
		m.roughness = 0.25
		m.clearcoat_enabled = true
		m.clearcoat = 0.7
		m.clearcoat_roughness = 0.15
		m.backlight_enabled = true
		m.backlight = (COLORS[ci] as Color).darkened(0.4)
		mat_cache[key] = m
	return mat_cache[key]


func rivet_mat() -> StandardMaterial3D:
	if not mat_cache.has("rivet"):
		var m := StandardMaterial3D.new()
		m.albedo_color = Color("dfe3ea")
		m.metallic = 1.0
		m.roughness = 0.22
		mat_cache["rivet"] = m
	return mat_cache["rivet"]


func tile_parts(shape: String) -> Dictionary:
	# Meshes modelled in Blender (art/src/tiles.py): Frame, Panel, Rivets.
	var key := "parts_" + shape
	if not mesh_cache.has(key):
		var scene: Node = (load("res://assets/tiles/%s.glb" % shape) as PackedScene).instantiate()
		var parts := {}
		for mi in scene.find_children("*", "MeshInstance3D", true, false):
			parts[(mi as Node).name] = (mi as MeshInstance3D).mesh
		scene.free()
		mesh_cache[key] = parts
	return mesh_cache[key]


# ---------------------------------------------------------------- tiles in the world

func spawn_tile(shape: String, color: int, xf: Transform3D) -> Dictionary:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	body.transform = xf
	var visual := Node3D.new()
	body.add_child(visual)
	var parts := tile_parts(shape)
	var mats := {"Frame": frame_mat(color), "Panel": panel_mat(color), "Rivets": rivet_mat()}
	for part in mats:
		var mi := MeshInstance3D.new()
		mi.mesh = parts[part]
		mi.material_override = mats[part]
		if part == "Panel":
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		visual.add_child(mi)
	var cs := CollisionShape3D.new()
	var shp := ConvexPolygonShape3D.new()
	var pts := PackedVector3Array()
	var wv := PackedVector3Array()
	for p in shape_verts(shape):
		pts.append(p + Vector3(0, T / 2, 0))
		pts.append(p - Vector3(0, T / 2, 0))
		wv.append(xf * p)
	shp.points = pts
	cs.shape = shp
	body.add_child(cs)
	add_child(body)
	var t := {"id": next_id, "shape": shape, "color": color, "xform": xf, "verts": wv, "node": body}
	next_id += 1
	body.set_meta("tile", t)
	tiles.append(t)
	# Little "pop" as it snaps in.
	visual.scale = Vector3(0.8, 0.8, 0.8)
	create_tween().tween_property(visual, "scale", Vector3.ONE, 0.18).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	return t

func remove_tile(t: Dictionary, record := true) -> void:
	for i in tiles.size():
		if tiles[i].id == t.id:
			tiles.remove_at(i)
			break
	(t.node as Node).queue_free()
	if record:
		undo_stack.append({"op": "remove", "shape": t.shape, "color": t.color, "xform": t.xform})
	play_sfx(pop_snd)
	hover_key = ""
	save_world()


func overlaps(xf: Transform3D, shape: String) -> bool:
	var c := xf.origin
	var n := xf.basis.y
	for o in tiles:
		var oc: Vector3 = o.xform.origin
		var d := c.distance_to(oc)
		if d < 0.2:
			return true
		var on: Vector3 = o.xform.basis.y
		var limit := 0.95 if (shape == "big" or o.shape == "big") else 0.5
		if absf(n.dot(on)) > 0.98 and absf((c - oc).dot(on)) < 0.05 and d < limit:
			return true
	return false


# ---------------------------------------------------------------- magnet snapping

func attach_frame(t: Dictionary, ei: int, hit: Vector3, shape: String) -> Dictionary:
	# Lay the new tile flat against edge `ei` of tile `t`, extending outward in
	# the same plane (fold angle 0). Folding then rotates it about that edge.
	var bv: PackedVector3Array = t.verts
	var n := bv.size()
	var p0 := bv[ei]
	var p1 := bv[(ei + 1) % n]
	var lb := p0.distance_to(p1)
	var u := (p1 - p0) / lb
	var nv := shape_verts(shape)
	var m := nv.size()
	var k := 0
	var best := INF
	for j in m:
		var d := absf(nv[j].distance_to(nv[(j + 1) % m]) - lb)
		if d < best - 0.001:
			best = d
			k = j
	var a := nv[k]
	var b := nv[(k + 1) % m]
	var ln := a.distance_to(b)
	# Mismatched edge lengths slide along each other in half-unit steps.
	var lo := minf(0.0, lb - ln)
	var hi := maxf(0.0, lb - ln)
	var along := clampf((hit - p0).dot(u), 0.0, lb)
	var s := clampf(snappedf(along - ln / 2, 0.5), lo, hi)
	var mid := p0 + u * (s + ln / 2)
	var w := mid - centroid(bv)
	w -= u * w.dot(u)
	var dbase := w.length()
	w /= dbase
	var ul := (b - a) / ln
	var ml := (a + b) / 2
	var il := centroid(nv) - ml
	il = (il - ul * il.dot(ul)).normalized()
	var lbasis := Basis(ul, Vector3.UP, il)
	var nw := w.cross(u)
	if lbasis.determinant() < 0:
		nw = -nw
	var r := Basis(u, nw, w) * lbasis.transposed()
	var ht := 0.0
	for p in nv:
		ht = maxf(ht, (p - ml).dot(il))
	return {
		"t0": Transform3D(r, mid - r * ml), "axis": u, "pivot": mid, "w": w,
		"dbase": dbase, "ht": ht, "hinge": [k, (k + 1) % m], "s": s,
	}


func folded(f: Dictionary, deg: float, side: Vector3) -> Transform3D:
	# Rotate about the hinge; positive degrees fold toward `side`.
	var u: Vector3 = f.axis
	var sgn := 1.0 if u.cross(f.w).dot(side) >= 0.0 else -1.0
	var rot := Basis(u, deg_to_rad(deg) * sgn)
	var piv: Vector3 = f.pivot
	return Transform3D(rot, piv - rot * piv) * (f.t0 as Transform3D)


func closing_err(f: Dictionary, deg: float, side: Vector3, free_local: Array, near: PackedVector3Array) -> float:
	var xf := folded(f, deg, side)
	var best := INF
	for p in free_local:
		var wp: Vector3 = xf * p
		for q in near:
			best = minf(best, wp.distance_squared_to(q))
	return sqrt(best)


func edge_candidates(t: Dictionary, ei: int, hit: Vector3, view_side: Vector3, shape: String) -> Array:
	var f := attach_frame(t, ei, hit, shape)
	var nv := shape_verts(shape)
	var is_tri := nv.size() == 3
	var free_local: Array = []
	for j in nv.size():
		if not (f.hinge as Array).has(j):
			free_local.append(nv[j])
	var piv: Vector3 = f.pivot
	var near := PackedVector3Array()
	for o in tiles:
		if (o.xform.origin as Vector3).distance_to(piv) > 3.0:
			continue
		for p in o.verts:
			if p.distance_to(piv) < 2.0:
				near.append(p)

	var base_n: Vector3 = t.xform.basis.y
	var base_c: Vector3 = t.xform.origin
	var horizontal := absf(base_n.y) > 0.7
	var hinge_top := absf((f.axis as Vector3).y) < 0.2 and (f.w as Vector3).y > 0.5
	# Which side of a wall is "inside"? Whichever side its neighbours are on.
	var side_in := -view_side
	var acc := Vector3.ZERO
	var cnt := 0
	for o in tiles:
		if o.id == t.id:
			continue
		var oc: Vector3 = o.xform.origin
		if oc.distance_to(base_c) < 1.6:
			acc += oc
			cnt += 1
	if cnt > 0:
		var d := (acc / cnt - base_c).dot(base_n)
		if absf(d) > 0.05:
			side_in = base_n * signf(d)
	# Pyramid on top of the base tile / pyramid roof over a 1-wide box.
	var lean_floor := 180.0 - rad_to_deg(acos(clampf(f.dbase / f.ht, 0.0, 1.0)))
	var lean_wall := 90.0 - rad_to_deg(acos(clampf(0.5 / f.ht, 0.0, 1.0)))

	var opts: Array = []  # [degrees, side]
	if horizontal:
		opts.append([lean_floor if is_tri else 90.0, view_side])
	elif is_tri and hinge_top:
		opts.append([lean_wall, side_in])
	else:
		opts.append([0.0, view_side])
	opts.append_array([[90.0, view_side], [0.0, view_side], [-90.0, view_side]])
	if is_tri:
		opts.append_array([[lean_floor, view_side], [lean_floor, -view_side], [lean_wall, side_in], [lean_wall, -side_in]])

	# Magnetic closings: angles where a free corner lands on an existing corner.
	var angles: Array = []
	var cluster: Array = []
	for deg in range(-175, 176):
		if closing_err(f, deg, view_side, free_local, near) < SNAP_EPS:
			cluster.append(deg)
		elif not cluster.is_empty():
			angles.append(refine(f, cluster, view_side, free_local, near))
			cluster = []
	if not cluster.is_empty():
		angles.append(refine(f, cluster, view_side, free_local, near))

	var xfs: Array = []
	for a in angles:
		xfs.append(folded(f, a, view_side))
	for o in opts:
		xfs.append(folded(f, o[0], o[1]))
	var out: Array = []
	for xf in xfs:
		var dup := false
		for e in out:
			if (e.origin as Vector3).distance_to(xf.origin) < 0.03:
				dup = true
				break
		if not dup and not overlaps(xf, shape):
			out.append(xf)
	return out


func refine(f: Dictionary, cluster: Array, side: Vector3, free_local: Array, near: PackedVector3Array) -> float:
	var lo := float(cluster[0]) - 1.0
	var hi := float(cluster[-1]) + 1.0
	for i in 40:
		var m1 := lo + (hi - lo) / 3.0
		var m2 := hi - (hi - lo) / 3.0
		if closing_err(f, m1, side, free_local, near) < closing_err(f, m2, side, free_local, near):
			hi = m2
		else:
			lo = m1
	return (lo + hi) / 2.0


func ground_candidates(hit: Vector3, shape: String) -> Array:
	var c: Vector3
	if shape == "big":
		c = Vector3(roundf(hit.x), 0, roundf(hit.z))
	else:
		c = Vector3(floorf(hit.x) + 0.5, 0, floorf(hit.z) + 0.5)
	var rot := Basis(Vector3.UP, ground_rot * PI / 2)
	var v := shape_verts(shape)
	var off := 0.5 - v[0].z if v.size() == 3 else 0.0  # triangle base sits on a grid line
	var xf := Transform3D(rot, c + rot * Vector3(0, 0, off) + Vector3(0, T / 2 + 0.002, 0))
	return [] if overlaps(xf, shape) else [xf]


func nearest_edge(t: Dictionary, p: Vector3) -> int:
	var v: PackedVector3Array = t.verts
	var best := INF
	var bi := 0
	for i in v.size():
		var q := Geometry3D.get_closest_point_to_segment(p, v[i], v[(i + 1) % v.size()])
		var d := q.distance_to(p)
		if d < best:
			best = d
			bi = i
	return bi


# ---------------------------------------------------------------- hover + placing

func update_hover() -> void:
	ghost.visible = false
	hover_tile = null
	if play_mode or get_viewport().gui_get_hovered_control() != null:
		return
	var mp := get_viewport().get_mouse_position()
	var from := cam.project_ray_origin(mp)
	var q := PhysicsRayQueryParameters3D.create(from, from + cam.project_ray_normal(mp) * 300.0, 1 | 2)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return
	var pos: Vector3 = hit.position
	var col: Object = hit.collider
	if col.has_meta("tile"):
		hover_tile = col.get_meta("tile")
		if erase_mode:
			ghost.mesh = panel_mesh(hover_tile.shape)
			ghost.material_override = erase_mat
			var xf: Transform3D = hover_tile.xform
			ghost.transform = Transform3D(xf.basis.scaled_local(Vector3(1.03, 1.6, 1.03)), xf.origin)
			ghost.visible = true
			return
		var ei := nearest_edge(hover_tile, pos)
		var n: Vector3 = hover_tile.xform.basis.y
		var view_side := n if n.dot(cam.global_position - pos) >= 0.0 else -n
		var s: float = attach_frame(hover_tile, ei, pos, cur_shape).s
		var key := "t%d:%d:%s:%.1f:%d:%d" % [hover_tile.id, ei, cur_shape, s, int(view_side.dot(n)), tiles.size()]
		if key != hover_key:
			hover_key = key
			hover_ground = false
			candidates = edge_candidates(hover_tile, ei, pos, view_side, cur_shape)
			cand_index = 0
	else:
		if erase_mode or pos.y < -0.05 or Vector2(pos.x, pos.z).length() > 6.6:
			return
		var key := "g%d:%d:%s:%d:%d" % [floori(pos.x * 2), floori(pos.z * 2), cur_shape, ground_rot, tiles.size()]
		if key != hover_key:
			hover_key = key
			hover_ground = true
			candidates = ground_candidates(pos, cur_shape)
			cand_index = 0
	if candidates.is_empty():
		return
	ghost.mesh = panel_mesh(cur_shape)
	ghost.material_override = ghost_mat
	ghost.transform = candidates[cand_index % candidates.size()]
	ghost.visible = true


func place_ghost() -> void:
	if not ghost.visible or candidates.is_empty():
		return
	var xf: Transform3D = candidates[cand_index % candidates.size()]
	var t := spawn_tile(cur_shape, cur_color, xf)
	undo_stack.append({"op": "add", "id": t.id})
	play_sfx(click_snd)
	hover_key = ""
	save_world()


func flip() -> void:
	if hover_ground:
		ground_rot = (ground_rot + 1) % 4
		hover_key = ""
	else:
		cand_index += 1


func undo() -> void:
	if undo_stack.is_empty():
		return
	var u: Dictionary = undo_stack.pop_back()
	if u.op == "add":
		for t in tiles:
			if t.id == u.id:
				remove_tile(t, false)
				break
	else:
		spawn_tile(u.shape, u.color, u.xform)
		play_sfx(click_snd)
		hover_key = ""
		save_world()


# ---------------------------------------------------------------- input + camera

func _unhandled_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton:
		var mb := ev as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed and not play_mode:
			if erase_mode:
				if hover_tile != null:
					remove_tile(hover_tile)
			else:
				place_ghost()
		elif mb.button_index == MOUSE_BUTTON_RIGHT:
			if mb.pressed:
				orbiting = true
				right_press_pos = mb.position
				right_moved = false
			else:
				orbiting = false
				if not right_moved and not play_mode and hover_tile != null:
					remove_tile(hover_tile)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			cam_dist = clampf(cam_dist * 0.9, 1.5, 40.0)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			cam_dist = clampf(cam_dist * 1.1, 1.5, 40.0)
	elif ev is InputEventMouseMotion:
		var mm := ev as InputEventMouseMotion
		if orbiting:
			cam_yaw -= mm.relative.x * 0.008
			cam_pitch = clampf(cam_pitch + mm.relative.y * 0.006, 0.05, 1.45)
			if mm.position.distance_to(right_press_pos) > 6.0:
				right_moved = true
	elif ev is InputEventPanGesture:
		var pg := ev as InputEventPanGesture
		cam_yaw -= pg.delta.x * 0.04
		cam_pitch = clampf(cam_pitch + pg.delta.y * 0.03, 0.05, 1.45)
	elif ev is InputEventMagnifyGesture:
		cam_dist = clampf(cam_dist / (ev as InputEventMagnifyGesture).factor, 1.5, 40.0)
	elif ev is InputEventKey and ev.pressed and not ev.echo:
		match (ev as InputEventKey).keycode:
			KEY_1, KEY_2, KEY_3, KEY_4:
				set_shape(SHAPES[(ev as InputEventKey).keycode - KEY_1])
			KEY_C:
				set_color((cur_color + 1) % COLORS.size())
			KEY_X:
				set_erase(not erase_mode)
			KEY_Z:
				undo()
			KEY_R:
				flip()
			KEY_TAB:
				set_play(not play_mode)


func _process(delta: float) -> void:
	if not play_mode:
		var fwd := Vector3(-sin(cam_yaw), 0, -cos(cam_yaw))
		var right := Vector3(cos(cam_yaw), 0, -sin(cam_yaw))
		var move := Vector3.ZERO
		if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
			move += fwd
		if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
			move -= fwd
		if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
			move -= right
		if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
			move += right
		cam_target += move * cam_dist * 0.6 * delta
	else:
		cam_target = cam_target.lerp(player.global_position + Vector3(0, 0.35, 0), 1.0 - exp(-10.0 * delta))
	if Input.is_key_pressed(KEY_Q):
		cam_yaw += 1.8 * delta
	if Input.is_key_pressed(KEY_E):
		cam_yaw -= 1.8 * delta

	var off := Vector3(cos(cam_pitch) * sin(cam_yaw), sin(cam_pitch), cos(cam_pitch) * cos(cam_yaw)) * cam_dist
	cam.global_position = cam_target + off
	cam.look_at(cam_target, Vector3.UP)

	update_hover()
	var c: Color = (COLORS[cur_color] as Color).lightened(0.35)
	c.a = 0.45 + 0.2 * sin(Time.get_ticks_msec() / 160.0)
	ghost_mat.albedo_color = c
	if ghost.visible and not hover_ground and candidates.size() > 1:
		status_label.text = "Way %d of %d  -  press R to flip" % [cand_index % candidates.size() + 1, candidates.size()]
	else:
		status_label.text = ""

	if shot_path != "":
		frame_count += 1
		if frame_count == 40:
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png(shot_path)
			get_tree().quit()


# ---------------------------------------------------------------- modes

func set_shape(s: String) -> void:
	cur_shape = s
	hover_key = ""
	set_erase(false)


func set_color(i: int) -> void:
	cur_color = i
	set_erase(false)


func set_erase(on: bool) -> void:
	erase_mode = on
	hover_key = ""
	refresh_ui()


func set_play(on: bool) -> void:
	play_mode = on
	if on:
		erase_mode = false
		var drop := cam_target + Vector3(0, 2.5, 0)
		player.spawn = drop
		player.global_position = drop
		player.velocity = Vector3.ZERO
		cam_dist = minf(cam_dist, 4.0)
	set_player_active(on)
	refresh_ui()


# ---------------------------------------------------------------- UI

func make_style(bg: Color, border: Color, bw: int) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.set_corner_radius_all(14)
	sb.set_border_width_all(bw)
	sb.border_color = border
	sb.set_content_margin_all(8)
	return sb


func style_button(b: Button, bg: Color, selected: bool) -> void:
	var border := Color.WHITE if selected else bg.darkened(0.25)
	var bw := 5 if selected else 2
	b.add_theme_stylebox_override("normal", make_style(bg, border, bw))
	b.add_theme_stylebox_override("hover", make_style(bg.lightened(0.15), border, bw))
	b.add_theme_stylebox_override("pressed", make_style(bg.darkened(0.15), border, bw))


func add_button(parent: Control, text: String, size: Vector2, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = size
	b.focus_mode = Control.FOCUS_NONE
	b.add_theme_font_size_override("font_size", 18)
	b.pressed.connect(cb)
	parent.add_child(b)
	return b


func setup_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)

	var bar := PanelContainer.new()
	bar.add_theme_stylebox_override("panel", make_style(Color(0, 0, 0, 0.35), Color(0, 0, 0, 0), 0))
	bar.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	bar.grow_horizontal = Control.GROW_DIRECTION_BOTH
	bar.grow_vertical = Control.GROW_DIRECTION_BEGIN
	bar.position.y -= 16
	layer.add_child(bar)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	bar.add_child(row)

	for s in SHAPES:
		shape_buttons[s] = add_button(row, SHAPE_LABELS[s], Vector2(96, 72), set_shape.bind(s))
	row.add_child(VSeparator.new())
	for i in COLORS.size():
		color_buttons.append(add_button(row, "", Vector2(56, 72), set_color.bind(i)))
	row.add_child(VSeparator.new())
	erase_button = add_button(row, "Eraser", Vector2(96, 72), func(): set_erase(not erase_mode))
	undo_button = add_button(row, "Undo", Vector2(80, 72), undo)
	play_button = add_button(row, "Play!", Vector2(110, 72), func(): set_play(not play_mode))

	hint_label = Label.new()
	hint_label.position = Vector2(18, 14)
	hint_label.add_theme_font_size_override("font_size", 15)
	hint_label.add_theme_color_override("font_color", Color.WHITE)
	hint_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	hint_label.add_theme_constant_override("outline_size", 5)
	layer.add_child(hint_label)

	status_label = Label.new()
	status_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	status_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	status_label.position.y = 16
	status_label.add_theme_font_size_override("font_size", 22)
	status_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	status_label.add_theme_constant_override("outline_size", 6)
	layer.add_child(status_label)


func refresh_ui() -> void:
	if shape_buttons.is_empty():
		return
	for s in SHAPES:
		style_button(shape_buttons[s], Color("3a4a63"), s == cur_shape and not erase_mode)
	for i in color_buttons.size():
		style_button(color_buttons[i], COLORS[i], i == cur_color and not erase_mode)
	style_button(erase_button, Color("b53a3a") if erase_mode else Color("3a4a63"), erase_mode)
	style_button(undo_button, Color("3a4a63"), false)
	play_button.text = "Build!" if play_mode else "Play!"
	style_button(play_button, Color("2f9e55"), false)
	if play_mode:
		hint_label.text = "WASD / arrows: walk   Space: jump   Right-drag or Q/E: turn camera   Tab: back to building"
	else:
		hint_label.text = "Click: place tile   Right-click: remove   R: flip   1-4: shape   C: colour   Z: undo\nRight-drag / two-finger swipe: spin   Scroll / pinch: zoom   WASD: move   Tab: play"


# ---------------------------------------------------------------- audio

func setup_audio() -> void:
	sfx = AudioStreamPlayer.new()
	add_child(sfx)
	click_snd = make_sound("click")
	pop_snd = make_sound("pop")


func make_sound(kind: String) -> AudioStreamWAV:
	var rate := 22050
	var n := int(rate * 0.14)
	var data := PackedByteArray()
	data.resize(n * 2)
	for i in n:
		var t := float(i) / rate
		var s := 0.0
		if kind == "click":
			# Two quick plastic clacks - the magnet pulling the tile in.
			s = sin(TAU * 1700.0 * t) * exp(-t * 60.0) + (randf() * 2.0 - 1.0) * exp(-t * 220.0) * 0.5
			if t > 0.035:
				var t2 := t - 0.035
				s += sin(TAU * 2300.0 * t2) * exp(-t2 * 70.0) * 0.8 + (randf() * 2.0 - 1.0) * exp(-t2 * 250.0) * 0.4
		else:
			s = sin(TAU * (520.0 - 1500.0 * t) * t) * exp(-t * 22.0)
		data.encode_s16(i * 2, int(clampf(s * 0.45, -1.0, 1.0) * 32767.0))
	var w := AudioStreamWAV.new()
	w.format = AudioStreamWAV.FORMAT_16_BITS
	w.mix_rate = rate
	w.data = data
	return w


func play_sfx(snd: AudioStream) -> void:
	sfx.stream = snd
	sfx.pitch_scale = randf_range(0.9, 1.12)
	sfx.play()


# ---------------------------------------------------------------- save / load

func save_world() -> void:
	if demo:
		return
	var arr: Array = []
	for t in tiles:
		var x: Transform3D = t.xform
		arr.append({"s": t.shape, "c": t.color, "x": [
			x.basis.x.x, x.basis.x.y, x.basis.x.z, x.basis.y.x, x.basis.y.y, x.basis.y.z,
			x.basis.z.x, x.basis.z.y, x.basis.z.z, x.origin.x, x.origin.y, x.origin.z]})
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(arr))


func load_world() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if typeof(data) != TYPE_ARRAY:
		return
	for d in data:
		var a: Array = d.x
		var xf := Transform3D(Vector3(a[0], a[1], a[2]), Vector3(a[3], a[4], a[5]), Vector3(a[6], a[7], a[8]), Vector3(a[9], a[10], a[11]))
		spawn_tile(d.s, int(d.c), xf)


# ---------------------------------------------------------------- demo build (for testing the snapping)

func demo_attach(base: Dictionary, which: String, shape: String, color: int, pick := 0) -> Dictionary:
	# Attach to the base tile's top-most ("top") or a specific-index edge, as if clicked from above.
	var v: PackedVector3Array = base.verts
	var ei := 0
	if which == "top":
		var best := -INF
		for i in v.size():
			var my := (v[i].y + v[(i + 1) % v.size()].y) / 2
			if my > best + 0.001:
				best = my
				ei = i
	else:
		ei = int(which)
	var mid := (v[ei] + v[(ei + 1) % v.size()]) / 2
	var n: Vector3 = base.xform.basis.y
	var cands := edge_candidates(base, ei, mid, n if n.y >= 0.0 else -n, shape)
	return spawn_tile(shape, color, cands[pick % cands.size()])


func build_demo() -> void:
	# A little house: floor, four walls (corners click together), pyramid roof.
	var floor_t := spawn_tile("square", 4, ground_candidates(Vector3(0.3, 0, 0.3), "square")[0])
	var walls: Array = []
	for i in 4:
		walls.append(demo_attach(floor_t, str(i), "square", [0, 2, 3, 6][i]))
	for i in 4:
		demo_attach(walls[i], "top", "triangle", [2, 0, 6, 3][i])
	# A tetrahedron next door.
	var tri := spawn_tile("triangle", 5, ground_candidates(Vector3(2.4, 0, 0.3), "triangle")[0])
	for i in 3:
		demo_attach(tri, str(i), "triangle", [1, 4, 6][i])
	# A tall-triangle pyramid on a big square.
	var big := spawn_tile("big", 2, ground_candidates(Vector3(-2.1, 0, 0.2), "big")[0])
	for i in 4:
		var cands := edge_candidates(big, i, (big.verts[i] + big.verts[(i + 1) % 4]) / 2, Vector3.UP, "big")
		spawn_tile("big", [0, 4, 3, 1][i], cands[0])
	print("demo tiles: ", tiles.size())
	cam_target = Vector3(0, 0.8, 0.5)
	cam_dist = 9.0
