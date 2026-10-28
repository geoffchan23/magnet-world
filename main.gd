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
const SHAPES := ["square", "triangle", "right", "tall", "big"]
const SAVE_PATH := "user://world.json"
const SETTINGS_PATH := "user://settings.json"
const CHARACTERS := ["kid", "fox", "robot", "dino"]
const CHARACTER_NAMES := {"kid": "Kid", "fox": "Fox", "robot": "Robot", "dino": "Dino"}
const BUILD_R := 12.5  # radius of the build area in the middle of the lot
const ITEMS := {
	"couch": {"name": "Our Living Room Couch", "scene": "res://assets/items/couch.glb",
		"icon": "res://assets/items/couch.png", "scale": 0.5},
}
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
var cam_target := Vector3(0.5, 0.0, 0.5)
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
var tilt := 0.0  # extra hinge angle (degrees) added with F / G - any angle you like
var hinge_pivot := Vector3.ZERO  # the edge the ghost tile swings around
var hinge_axis := Vector3.RIGHT
var near_verts := PackedVector3Array()  # corners nearby, for magnetic sticking while tilting
var ghost_xf := Transform3D()  # what Space will actually place
var ghost_ok := true
var ghost_snapped := false
var shown_tilt := 0.0
var bad_mat: StandardMaterial3D

var player: CharacterBody3D
var city: Node3D  # city.gd
var buggy: Node3D  # vehicle.gd: the one parked by the lot at the start
var rides: Array = []  # every vehicle out in the world
var ride: Node3D  # the one you're driving (vehicle.gd or flyer.gd)
const Rides := preload("res://rides.gd")
const MAX_RIDES := 6
var driving := false
var combat: Node3D  # combat.gd: weapons, shots, explosions
var encounters: Node3D  # encounters.gd: people, creatures and scenarios
const MAX_HEARTS := 6
var hearts := MAX_HEARTS
var stars := 0
var heal_t := 0.0  # hearts come back one at a time when nothing has hit you for a while
var hearts_label: Label
var banner_label: Label
var weapon_bar: HBoxContainer
var weapon_buttons := {}
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
var char_button: Button
var picker: Control
var shape_buttons := {}
var color_buttons: Array = []

var items: Array = []  # placed things from the Items menu: {id, item, xform, node}
var place_item := ""  # item being placed right now ("" = building with tiles)
var item_rot := 0  # 45-degree steps
var item_ghost: Node3D
var item_ghost_xf := Transform3D()
var item_ghost_ok := false
var hover_item = null
var lit_item = null
var items_menu: Control
var smash_menu: Control
var smash_button: Button
var destroyer: Node3D  # destroy.gd: the Smash! shows
var busy := false  # a smash show is playing; building/walking input is paused
var shake := 0.0  # camera shake amount, decays by itself
var crash_snd: AudioStreamWAV
var thud_snd: AudioStreamWAV
var items_button: Button
var kb_aim := true  # aim with the keyboard crosshair instead of the mouse
var aim_pos := Vector2(-1, -1)  # crosshair position on screen (WASD moves it)
var crosshair: Control
var help_panel: PanelContainer
var help_grid: GridContainer
var help_visible := true
var flip_button: Button
var picker_sel := 0
var flash_text := ""
var flash_until := 0

var demo := false
var city_seed := 0  # every world gets its own random city; it's kept in the save
var no_save := false
var key_script: Array = []
var shot_frame := 40
var shot_path := ""
var frame_count := 0
var cam_override := PackedFloat64Array()


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--demo":
			demo = true
		elif a.begins_with("--shot="):
			shot_path = a.substr(7)
		elif a.begins_with("--keys="):
			no_save = true  # scripted test runs never touch the real save
			# e.g. --keys=d:20,space:1  (key name : frames held), for testing keyboard play
			for step in a.substr(7).split(","):
				var kv := step.split(":")
				key_script.append([OS.find_keycode_from_string(kv[0]), int(kv[1]) if kv.size() > 1 else 1])
		elif a.begins_with("--shotframe="):
			shot_frame = int(a.substr(12))
		elif a.begins_with("--cam="):
			cam_override = a.substr(6).split_floats(",")
		elif a.begins_with("--seed="):
			city_seed = int(a.substr(7))
	if city_seed == 0:
		city_seed = 2026 if demo else saved_seed()
	setup_world()
	setup_ghost()
	setup_audio()
	setup_player()
	setup_buggy()
	combat = Node3D.new()
	combat.set_script(preload("res://combat.gd"))
	combat.main = self
	add_child(combat)
	encounters = Node3D.new()
	encounters.set_script(preload("res://encounters.gd"))
	encounters.main = self
	add_child(encounters)
	destroyer = Node3D.new()
	destroyer.set_script(preload("res://destroy.gd"))
	destroyer.main = self
	add_child(destroyer)
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
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--char="):
			player.set_character(a.substr(7))
		elif a == "--picker":
			show_picker(true)
		elif a.begins_with("--smash="):
			destroyer.start.call_deferred(a.substr(8))
		elif a == "--walk":
			player.auto_walk = true
		elif a.begins_with("--buggy="):
			var v := a.substr(8).split_floats(",")  # x,z,heading in degrees
			buggy.global_transform = Transform3D(Basis(Vector3.UP, deg_to_rad(v[2])), Vector3(v[0], 0.4, v[1]))
		elif a.begins_with("--ride="):
			set_play(true)
			summon_ride(a.substr(7))
		elif a == "--lineup":
			# Testing: every person and creature in a row, frozen mid-walk.
			var i := 0
			for k in preload("res://npc.gd").KINDS:
				var n: Node3D = encounters.spawn(k, cam_target + Vector3((i - 4) * 0.75, 0.05, 0))
				n.visual.rotation.y = PI
				n.set_physics_process(false)
				n.animate(0.12, 1.0)
				i += 1
		elif a.begins_with("--scenario="):
			encounters.force_next = a.substr(11)
		elif a == "--drive":
			set_play(true)
			enter_buggy(buggy)
	if "--play" in OS.get_cmdline_user_args():
		set_play(true)
	refresh_ui()
	if not key_script.is_empty():
		run_key_script.call_deferred()


# ---------------------------------------------------------------- world setup

func setup_world() -> void:
	var env := Environment.new()
	var sky_mat := PanoramaSkyMaterial.new()
	sky_mat.panorama = load("res://assets/textures/wasteland_sky.hdr")
	sky_mat.energy_multiplier = 1.0
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.75
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.05
	env.glow_enabled = true
	env.glow_intensity = 0.4
	env.glow_hdr_threshold = 1.2
	# Dusty haze: the far city fades into it.
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color("cdb894")
	env.fog_depth_begin = 30.0
	env.fog_depth_end = 300.0
	env.fog_depth_curve = 1.6
	env.fog_density = 0.6
	env.fog_sky_affect = 0.25
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.08
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38, -35, 0)
	sun.light_energy = 1.7
	sun.light_color = Color("ffe6c4")
	sun.shadow_enabled = true
	sun.shadow_blur = 1.5
	sun.directional_shadow_max_distance = 70.0
	add_child(sun)

	city = Node3D.new()
	city.set_script(preload("res://city.gd"))
	add_child(city)
	city.build(city_seed)
	scatter_grass.call_deferred()

	cam = Camera3D.new()
	cam.fov = 55
	cam.far = 700
	add_child(cam)


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
	# Dry weeds: around the edge of the building lot, along the kerbs and out in
	# the wasteland. Wait for the ground collision to exist first.
	await get_tree().physics_frame
	await get_tree().physics_frame
	var space := get_world_3d().direct_space_state
	var rng := RandomNumberGenerator.new()
	rng.seed = 42
	var xforms: Array = []
	var colors: Array = []
	var edge: float = city.CITY_HALF
	for i in 40000:
		if xforms.size() >= 7000:
			break
		var p := Vector3(rng.randf_range(-edge - 30, edge + 30), 3.0, rng.randf_range(-edge - 30, edge + 30))
		var lot: bool = maxf(absf(p.x), absf(p.z)) < city.LOT_HALF
		if lot:
			if Vector2(p.x, p.z).length() < BUILD_R + 0.3 and rng.randf() > 0.01:
				continue  # keep the build area clear
		elif maxf(absf(p.x), absf(p.z)) < edge and rng.randf() > 0.12:
			continue  # only a few weeds poke through the city
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(p, p + Vector3.DOWN * 6.0, 2))
		if hit.is_empty() or (hit.normal as Vector3).y < 0.8 or (hit.position as Vector3).y > 0.2:
			continue
		var s := rng.randf_range(0.7, 1.5)
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.8, 1.4), s))
		xforms.append(Transform3D(basis, hit.position))
		var g := rng.randf_range(0.8, 1.15)
		colors.append(Color(g * rng.randf_range(0.95, 1.15), g, g * 0.85))
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
	mat.set_shader_parameter("root_color", Color("4a4224"))
	mat.set_shader_parameter("tip_color", Color("b8a35e"))
	mmi.material_override = mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mmi)


func setup_ghost() -> void:
	ghost_mat = StandardMaterial3D.new()
	ghost_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ghost_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ghost_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	bad_mat = ghost_mat.duplicate()
	bad_mat.albedo_color = Color(1.0, 0.3, 0.25, 0.5)
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
	player.collision_mask = 1 | 2 | 32 | 64  # tiles, ground, the buggy, loose junk
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.14
	cap.height = 0.55
	cs.shape = cap
	cs.position.y = 0.275
	player.add_child(cs)
	var visual := Node3D.new()
	visual.name = "Visual"
	player.add_child(visual)
	add_child(player)
	player.set_character(load_settings().get("character", "kid"))
	set_player_active(false)

func setup_buggy() -> void:
	# Parked on the road just south of the lot, pointing east.
	buggy = make_ride("buggy", Transform3D(Basis(Vector3.UP, PI / 2), Vector3(-5.0, 0.4, city.LOT_HALF + city.ROAD / 2)))


func make_ride(kind: String, at: Transform3D) -> Node3D:
	var r: Node3D
	if Rides.RIDES[kind].type == "car":
		r = VehicleBody3D.new()
		r.set_script(preload("res://vehicle.gd"))
	else:
		r = CharacterBody3D.new()
		r.set_script(preload("res://flyer.gd"))
	r.main = self
	add_child(r)
	r.setup(at, kind)
	rides.append(r)
	return r


func summon_ride(kind: String) -> void:
	# From the Items menu: it appears next to you and in you hop.
	if driving:
		exit_buggy()
	if not play_mode:
		set_play(true)
	var here := player.global_position
	var fwd := Vector3(-sin(cam_yaw), 0, -cos(cam_yaw))  # facing the way you're looking
	var spot := here + fwd * 2.2
	var space := get_world_3d().direct_space_state
	for i in 8:
		var a := atan2(fwd.x, fwd.z) + i * PI / 4
		var p := here + Vector3(sin(a), 0, cos(a)) * 2.4
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(p.x, 30, p.z), Vector3(p.x, -2, p.z), 1 | 2))
		if not hit.is_empty() and (hit.position as Vector3).y < 0.3:
			spot = hit.position
			break
	var r := make_ride(kind, Transform3D(Basis(Vector3.UP, atan2(fwd.x, fwd.z)), spot + Vector3(0, 0.4, 0)))
	combat.sparkles(spot + Vector3(0, 0.6, 0), Color("ffffff"), 40)
	# Too many about? The oldest one you're not using drives off into the haze.
	while rides.size() > MAX_RIDES:
		var old: Node3D = rides.pop_front()
		if old == r:
			rides.append(old)
			break
		old.queue_free()
	enter_buggy(r)
	flash("%s!  %s  -  G to honk" % [Rides.RIDES[kind].name, Rides.SPECIAL_TEXT[Rides.RIDES[kind].special]])


func player_body() -> Node3D:
	# Where "you" are: your explorer, or the vehicle you're driving.
	return ride if driving else player


func on_foot() -> bool:
	return play_mode and not driving and not busy


func driven_vehicle() -> Node3D:
	return ride if driving else null


func hurt_player(damage: int, from: Vector3) -> void:
	if player.hurt_t > 0.0:
		return  # just got hit: a moment to get away
	hearts -= damage
	var away := player.global_position - from
	away.y = 0
	player.velocity = away.normalized() * 4.0 + Vector3(0, 3.0, 0)
	player.hurt_t = 1.0
	heal_t = 0.0
	shake = 0.35
	play_sfx(thud_snd)
	combat.sparkles(player.global_position + Vector3(0, 0.3, 0), Color("ff6060"), 10, 0.5)
	if hearts <= 0:
		# Out of hearts: back to the building lot, all better.
		banner("Ouch! Back to base to heal up.")
		hearts = MAX_HEARTS
		player.global_position = Vector3(0, 1.0, 0)
		player.velocity = Vector3.ZERO
		for n in get_tree().get_nodes_in_group("npc"):
			if not n.friendly and (n as Node3D).global_position.length() < 25.0:
				n.queue_free()
	refresh_hud()


func sparkle_burst(at: Vector3, col: Color) -> void:
	combat.sparkles(at, col, 30)


func add_stars(n: int, at: Vector3) -> void:
	stars += n
	combat.sparkles(at + Vector3(0, 0.5, 0), Color("ffd84a"), 12 * n)
	play_sfx(click_snd)
	refresh_hud()


func banner(text: String) -> void:
	banner_label.text = text
	banner_label.modulate.a = 1.0
	banner_label.scale = Vector2(0.6, 0.6)
	var tw := create_tween()
	tw.tween_property(banner_label, "scale", Vector2.ONE, 0.25).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_interval(3.0)
	tw.tween_property(banner_label, "modulate:a", 0.0, 0.6)


func refresh_hud() -> void:
	if hearts_label == null:
		return
	hearts_label.text = "♥".repeat(maxi(hearts, 0)) + "♡".repeat(MAX_HEARTS - maxi(hearts, 0)) + "    ★ %d" % stars
	hearts_label.visible = play_mode
	weapon_bar.get_parent().visible = play_mode and not driving
	for w in weapon_buttons:
		style_button(weapon_buttons[w], Color("3a4a63"), w == combat.current)


func near_buggy() -> bool:
	return nearest_ride() != null


func nearest_ride() -> Node3D:
	if not play_mode or driving:
		return null
	var best: Node3D = null
	var best_d := 2.2
	for r in rides:
		var d := player.global_position.distance_to((r as Node3D).global_position)
		if d < best_d:
			best = r
			best_d = d
	return best


func enter_buggy(r: Node3D = null) -> void:
	if r == null:
		r = nearest_ride()
	if r == null:
		return
	ride = r
	driving = true
	ride.driving = true
	ride.set_driver(player.character)
	set_player_active(false)
	cam_dist = maxf(cam_dist, 5.5)
	cam_pitch = 0.32
	play_sfx(pop_snd)
	refresh_ui()


func exit_buggy() -> void:
	driving = false
	ride.driving = false
	ride.set_driver("")
	# Hop out on the driver's side (straight down if you're flying: it lands itself).
	var side: Vector3 = ride.global_basis.x
	var out: Vector3 = ride.global_position + side * 1.0 + Vector3(0, 0.6, 0)
	player.global_position = out
	player.velocity = Vector3.ZERO
	set_player_active(true)
	cam_dist = minf(cam_dist, 4.0)
	play_sfx(pop_snd)
	refresh_ui()


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
		"right":
			# Half a square (Picasso Tiles style): two unit legs and a long sloped side.
			return PackedVector3Array([Vector3(-1.0 / 3, 0, 1.0 / 3), Vector3(2.0 / 3, 0, 1.0 / 3), Vector3(-1.0 / 3, 0, -2.0 / 3)])
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

func remove_tile(t: Dictionary, record := true, quiet := false) -> void:
	for i in tiles.size():
		if tiles[i].id == t.id:
			tiles.remove_at(i)
			break
	(t.node as Node).queue_free()
	if record:
		undo_stack.append({"op": "remove", "shape": t.shape, "color": t.color, "xform": t.xform})
	hover_key = ""
	if quiet:
		return
	play_sfx(pop_snd)
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

func matching_edges(shape: String, lb: float) -> Array:
	# Edges of `shape` whose length best matches lb (several when sides are equal).
	var nv := shape_verts(shape)
	var m := nv.size()
	var best := INF
	for j in m:
		best = minf(best, absf(nv[j].distance_to(nv[(j + 1) % m]) - lb))
	var ks: Array = []
	for j in m:
		if absf(nv[j].distance_to(nv[(j + 1) % m]) - lb) < best + 0.01:
			ks.append(j)
	return ks


func attach_frame(t: Dictionary, ei: int, hit: Vector3, shape: String, k := -1) -> Dictionary:
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
	if k < 0:
		k = matching_edges(shape, lb)[0]
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
	var bv: PackedVector3Array = t.verts
	var lb := bv[ei].distance_to(bv[(ei + 1) % bv.size()])
	var closings: Array = []
	var per_edge: Array = []
	for k in matching_edges(shape, lb):
		var parts := hinge_candidates(t, ei, hit, view_side, shape, k)
		closings.append_array(parts[0])
		per_edge.append(parts[1])
	# Interleave the presets so R flips to the mirror image first (right triangle).
	var others: Array = []
	for i in per_edge[0].size():
		for opts in per_edge:
			if i < opts.size():
				others.append(opts[i])
	var out: Array = []
	for xf in closings + others:
		if out.size() >= 8:
			break
		var dup := false
		for e in out:
			if (e.origin as Vector3).distance_to(xf.origin) < 0.03:
				dup = true
				break
		if not dup and not overlaps(xf, shape):
			out.append(xf)
	return out


func hinge_candidates(t: Dictionary, ei: int, hit: Vector3, view_side: Vector3, shape: String, k: int) -> Array:
	# [magnetic closings, preset folds] for one way of putting the new tile's edge k on the hinge.
	var f := attach_frame(t, ei, hit, shape, k)
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
		opts.append_array([[lean_floor, view_side], [lean_wall, side_in]])

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

	var closing_xfs: Array = []
	for a in angles:
		closing_xfs.append(folded(f, a, view_side))
	var opt_xfs: Array = []
	for o in opts:
		opt_xfs.append(folded(f, o[0], o[1]))
	return [closing_xfs, opt_xfs]


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
	var off := Vector3.ZERO
	if v.size() == 3:  # triangle base sits on a grid line, centred across the cell
		var minx := minf(v[0].x, minf(v[1].x, v[2].x))
		var maxx := maxf(v[0].x, maxf(v[1].x, v[2].x))
		off = Vector3(-(minx + maxx) / 2, 0, 0.5 - v[0].z)
	var xf := Transform3D(rot, c + rot * off + Vector3(0, T / 2 + 0.002, 0))
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
	hover_item = null
	if busy:
		return
	if item_ghost:
		item_ghost.visible = false
	update_item_hover()
	if play_mode or menu_open() or place_item != "":
		return
	if not kb_aim and get_viewport().gui_get_hovered_control() != null:
		return
	var mp := aim_pos if kb_aim else get_viewport().get_mouse_position()
	var from := cam.project_ray_origin(mp)
	var q := PhysicsRayQueryParameters3D.create(from, from + cam.project_ray_normal(mp) * 300.0, 1 | 2)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return
	var pos: Vector3 = hit.position
	var col: Object = hit.collider
	if col.has_meta("item"):
		hover_item = col.get_meta("item")  # removable (Backspace / eraser), never built on
		return
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
			tilt = 0.0
			var bv: PackedVector3Array = hover_tile.verts
			hinge_pivot = bv[ei]
			hinge_axis = (bv[(ei + 1) % bv.size()] - bv[ei]).normalized()
			gather_near_verts(hinge_pivot)
	else:
		if erase_mode or pos.y < -0.05 or Vector2(pos.x, pos.z).length() > BUILD_R:
			return
		var key := "g%d:%d:%s:%d:%d" % [floori(pos.x * 2), floori(pos.z * 2), cur_shape, ground_rot, tiles.size()]
		if key != hover_key:
			hover_key = key
			hover_ground = true
			candidates = ground_candidates(pos, cur_shape)
			cand_index = 0
			tilt = 0.0
			if not candidates.is_empty():
				ground_hinge(candidates[0])
				gather_near_verts(hinge_pivot)
	if candidates.is_empty():
		return
	var base: Transform3D = candidates[cand_index % candidates.size()]
	ghost_xf = base
	ghost_ok = true
	ghost_snapped = false
	if absf(tilt) > 0.01:
		# Swing the tile around its hinge to the chosen angle. It settles on
		# 45-degree steps (e.g. straight up) when close, and corners that come
		# close to other corners stick (magnets!).
		var want := tilt
		if absf(tilt - snappedf(tilt, 45.0)) < 4.0:
			want = snappedf(tilt, 45.0)
		var best := want
		var best_err := corner_err(tilted(base, want))
		for i in range(-10, 11):
			var a := tilt + i * 0.5
			var e := corner_err(tilted(base, a))
			if e < best_err:
				best_err = e
				best = a
		if best_err < 0.04:
			ghost_snapped = true
		else:
			best = want
		shown_tilt = best
		ghost_xf = tilted(base, best)
		ghost_ok = not overlaps(ghost_xf, cur_shape)
	ghost.mesh = panel_mesh(cur_shape)
	ghost.material_override = ghost_mat if ghost_ok else bad_mat
	ghost.transform = ghost_xf
	ghost.visible = true


func tilted(xf: Transform3D, deg: float) -> Transform3D:
	var r := Basis(hinge_axis, deg_to_rad(deg))
	return Transform3D(r, hinge_pivot - r * hinge_pivot) * xf


func ground_hinge(xf: Transform3D) -> void:
	# A tile on the ground tilts up around its back edge (the one on the grid line).
	var v := shape_verts(cur_shape)
	var n := v.size()
	var bi := 0
	for i in n:
		if v[i].z + v[(i + 1) % n].z > v[bi].z + v[(bi + 1) % n].z:
			bi = i
	var a: Vector3 = xf * v[bi]
	var b: Vector3 = xf * v[(bi + 1) % n]
	hinge_pivot = a
	hinge_axis = (b - a).normalized()
	# Positive tilt should lift the tile off the ground, not push it into it.
	if (tilted(xf, 10.0).origin.y) < xf.origin.y:
		hinge_axis = -hinge_axis


func gather_near_verts(around: Vector3) -> void:
	near_verts = PackedVector3Array()
	for o in tiles:
		for p in o.verts:
			if p.distance_to(around) < 3.0:
				near_verts.append(p)


func corner_err(xf: Transform3D) -> float:
	# How close the tile's free corners (not on the hinge) come to existing corners.
	var best := INF
	for p in shape_verts(cur_shape):
		var wp := xf * p
		var off := wp - hinge_pivot
		if (off - hinge_axis * off.dot(hinge_axis)).length() < 0.05:
			continue  # on the hinge itself
		for q in near_verts:
			best = minf(best, wp.distance_squared_to(q))
	return sqrt(best)


func place_ghost() -> void:
	if not ghost.visible or candidates.is_empty():
		return
	if not ghost_ok:
		flash("That would bump into another tile - tilt it some more")
		return
	var xf := ghost_xf
	var t := spawn_tile(cur_shape, cur_color, xf)
	undo_stack.append({"op": "add", "id": t.id})
	play_sfx(click_snd)
	hover_key = ""
	save_world()


func action() -> void:
	# Space / left-click: place the tile (or remove one in eraser mode).
	if place_item != "":
		place_item_here()
	elif erase_mode:
		remove_hovered()
	else:
		place_ghost()


func remove_hovered() -> void:
	if hover_tile != null:
		remove_tile(hover_tile)
	elif hover_item != null:
		remove_item(hover_item)


func flip() -> void:
	if place_item != "":
		item_rot = (item_rot + 1) % 8
	elif hover_ground:
		ground_rot = (ground_rot + 1) % 4
		hover_key = ""
	elif candidates.size() > 1:
		cand_index += 1
		tilt = 0.0
	elif ghost.visible:
		flash("This piece only fits one way here")


func flash(text: String) -> void:
	flash_text = text
	flash_until = Time.get_ticks_msec() + 1800


func undo() -> void:
	if undo_stack.is_empty():
		return
	var u: Dictionary = undo_stack.pop_back()
	if u.op == "add":
		for t in tiles:
			if t.id == u.id:
				remove_tile(t, false)
				break
	elif u.op == "destroy":
		destroyer.clear_debris()
		for d in u.tiles:
			spawn_tile(d.shape, d.color, d.xform)
		play_sfx(click_snd)
		flash("Rebuilt!")
		hover_key = ""
		save_world()
	elif u.op == "add_item":
		for it in items:
			if it.id == u.id:
				remove_item(it, false)
				break
	elif u.op == "remove_item":
		spawn_item(u.item, u.xform)
		play_sfx(click_snd)
		save_world()
	else:
		spawn_tile(u.shape, u.color, u.xform)
		play_sfx(click_snd)
		hover_key = ""
		save_world()


# ---------------------------------------------------------------- items (couch etc.)

func fabric_mat() -> StandardMaterial3D:
	if not mat_cache.has("fabric"):
		var m := StandardMaterial3D.new()
		m.albedo_color = Color("cdbfa6")  # warm cream, like the real couch
		m.roughness = 1.0
		m.metallic_specular = 0.2
		m.normal_enabled = true
		m.normal_texture = load("res://assets/textures/fabric_normal.jpg")
		m.normal_scale = 0.8
		m.uv1_triplanar = true
		m.uv1_scale = Vector3(5, 5, 5)
		mat_cache["fabric"] = m
	return mat_cache["fabric"]


func make_item_node(item: String, ghost_look: bool) -> Node3D:
	# The model is re-centred so it turns around its middle.
	var info: Dictionary = ITEMS[item]
	var root: Node3D = Node3D.new() if ghost_look else StaticBody3D.new()
	var model: Node3D = (load(info.scene) as PackedScene).instantiate()
	model.scale = Vector3.ONE * float(info.scale)
	root.add_child(model)
	var box := AABB()
	var first := true
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		var local := model.transform * m.transform
		var b := local * m.get_aabb()
		box = b if first else box.merge(b)
		first = false
		if ghost_look:
			m.material_override = mat_cache["item_ghost"]
			m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		else:
			for i in m.mesh.get_surface_count():
				var src := m.mesh.surface_get_material(i)
				if src and src.resource_name == "Fabric":
					m.set_surface_override_material(i, fabric_mat())
			var cs := CollisionShape3D.new()
			cs.shape = m.mesh.create_convex_shape()
			cs.transform = local
			root.add_child(cs)
	var centre := box.get_center()
	model.position -= Vector3(centre.x, 0, centre.z)
	for c in root.get_children():
		if c is CollisionShape3D:
			(c as Node3D).position -= Vector3(centre.x, 0, centre.z)
	if root is StaticBody3D:
		(root as StaticBody3D).collision_layer = 1
		(root as StaticBody3D).collision_mask = 0
	return root


func spawn_item(item: String, xf: Transform3D) -> Dictionary:
	var node := make_item_node(item, false)
	node.transform = xf
	add_child(node)
	var it := {"id": next_id, "item": item, "xform": xf, "node": node}
	next_id += 1
	node.set_meta("item", it)
	items.append(it)
	return it


func remove_item(it: Dictionary, record := true) -> void:
	for i in items.size():
		if items[i].id == it.id:
			items.remove_at(i)
			break
	if lit_item != null and lit_item.id == it.id:
		lit_item = null
	(it.node as Node).queue_free()
	if record:
		undo_stack.append({"op": "remove_item", "item": it.item, "xform": it.xform})
	play_sfx(pop_snd)
	save_world()


func set_place_item(item: String) -> void:
	place_item = item
	item_rot = 0
	if item_ghost:
		item_ghost.queue_free()
		item_ghost = null
	if item != "":
		if not mat_cache.has("item_ghost"):
			var gm := StandardMaterial3D.new()
			gm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			gm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			gm.albedo_color = Color(0.85, 0.93, 1.0, 0.5)
			mat_cache["item_ghost"] = gm
		erase_mode = false
		item_ghost = make_item_node(item, true)
		item_ghost.visible = false
		add_child(item_ghost)
	hover_key = ""
	refresh_ui()


func update_item_hover() -> void:
	# Ghost of the item being placed follows the aim along the ground (snaps to half-tiles).
	if place_item == "" or play_mode or menu_open() or item_ghost == null:
		return
	var mp := aim_pos if kb_aim else get_viewport().get_mouse_position()
	var from := cam.project_ray_origin(mp)
	var q := PhysicsRayQueryParameters3D.create(from, from + cam.project_ray_normal(mp) * 300.0, 2)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return
	var pos: Vector3 = hit.position
	item_ghost_xf = Transform3D(Basis(Vector3.UP, item_rot * PI / 4), Vector3(snappedf(pos.x, 0.5), 0.0, snappedf(pos.z, 0.5)))
	item_ghost_ok = pos.y > -0.05 and Vector2(pos.x, pos.z).length() < BUILD_R - 0.6
	for it in items:
		if (it.xform.origin as Vector3).distance_to(item_ghost_xf.origin) < 0.9:
			item_ghost_ok = false
	(mat_cache["item_ghost"] as StandardMaterial3D).albedo_color = Color(0.85, 0.93, 1.0, 0.5) if item_ghost_ok else Color(1.0, 0.35, 0.3, 0.5)
	item_ghost.transform = item_ghost_xf
	item_ghost.visible = true


func highlight_item(it) -> void:
	# Red tint on the item the eraser is pointing at.
	if lit_item == it or (lit_item != null and it != null and lit_item.id == it.id):
		return
	for target in [lit_item, it]:
		if target == null:
			continue
		for mi in (target.node as Node).find_children("*", "MeshInstance3D", true, false):
			(mi as MeshInstance3D).material_overlay = erase_mat if target == it else null
	lit_item = it


func place_item_here() -> void:
	if item_ghost == null or not item_ghost.visible:
		return
	if not item_ghost_ok:
		flash("It doesn't fit there - try another spot")
		return
	var it := spawn_item(place_item, item_ghost_xf)
	undo_stack.append({"op": "add_item", "id": it.id})
	play_sfx(click_snd)
	save_world()
	flash("%s added!" % ITEMS[place_item].name)
	set_place_item("")


func menu_open() -> bool:
	return picker.visible or items_menu.visible or smash_menu.visible


func build_card_menu(layer: CanvasLayer, title_text: String, entries: Array, pick: Callable) -> Control:
	# Full-screen chooser: one big picture card per entry {id, name, icon}.
	# Number keys pick directly; arrows + Enter also work; Esc closes.
	var menu := ColorRect.new()
	menu.color = Color(0.05, 0.08, 0.15, 0.55)
	menu.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	menu.mouse_filter = Control.MOUSE_FILTER_STOP
	menu.visible = false
	menu.set_meta("entries", entries)
	menu.set_meta("pick", pick)
	menu.set_meta("sel", 0)
	layer.add_child(menu)
	var centre := CenterContainer.new()
	centre.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	menu.add_child(centre)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 22)
	centre.add_child(col)
	var title := Label.new()
	title.text = title_text
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 44)
	title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.5))
	title.add_theme_constant_override("outline_size", 10)
	col.add_child(title)
	# A row of big cards, or a grid of smaller ones when there are lots.
	var many := entries.size() > 4
	var row := GridContainer.new()
	row.columns = mini(entries.size(), 7) if many else entries.size()
	row.add_theme_constant_override("h_separation", 14 if many else 22)
	row.add_theme_constant_override("v_separation", 14)
	var row_wrap := CenterContainer.new()
	row_wrap.add_child(row)
	col.add_child(row_wrap)
	menu.set_meta("columns", row.columns)
	for i in entries.size():
		var e: Dictionary = entries[i]
		var b := Button.new()
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(180, 200) if many else Vector2(340, 360)
		if ResourceLoader.exists(e.icon):
			b.icon = load(e.icon)
		b.expand_icon = true
		b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
		b.text = ("%d  %s" % [i + 1, e.name]) if i < 9 else e.name
		b.add_theme_font_size_override("font_size", 17 if many else 24)
		b.clip_text = true
		b.add_theme_color_override("font_color", Color("1d2a40"))
		b.add_theme_color_override("font_hover_color", Color("1d2a40"))
		b.set_meta("index", i)
		b.pressed.connect(func(): pick_from_menu(menu, i))
		row.add_child(b)
	var how := Label.new()
	how.text = "Press the number  -  or use the arrow keys and Enter"
	if entries.size() > 9:
		how.text = "Use the arrow keys and Enter (or press 1 - 9)"
	how.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	how.add_theme_font_size_override("font_size", 22)
	how.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.5))
	how.add_theme_constant_override("outline_size", 6)
	col.add_child(how)
	var close := add_button(col, "Esc  Close", Vector2(170, 64), func(): show_menu(menu, false))
	close.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	style_button(close, Color("3a4a63"), false)
	return menu


func show_menu(menu: Control, on: bool) -> void:
	menu.visible = on
	if on:
		for b in menu.find_children("*", "Button", true, false):
			if (b as Node).has_meta("index"):
				var sel: bool = b.get_meta("index") == menu.get_meta("sel")
				style_button(b, Color("ffffff") if sel else Color("c9d3e3"), sel)
				(b as Button).get_theme_stylebox("normal").border_color = Color("ffb400") if sel else Color("9aa7bd")
				(b as Button).get_theme_stylebox("normal").set_border_width_all(8 if sel else 2)


func menu_key(menu: Control, key: int) -> void:
	var n: int = (menu.get_meta("entries") as Array).size()
	if key >= KEY_1 and key <= KEY_9 and key - KEY_1 < n:
		pick_from_menu(menu, key - KEY_1)
		return
	match key:
		KEY_LEFT, KEY_A:
			menu.set_meta("sel", (int(menu.get_meta("sel")) + n - 1) % n)
			show_menu(menu, true)
		KEY_RIGHT, KEY_D:
			menu.set_meta("sel", (int(menu.get_meta("sel")) + 1) % n)
			show_menu(menu, true)
		KEY_UP, KEY_W:
			menu.set_meta("sel", (int(menu.get_meta("sel")) - int(menu.get_meta("columns", n)) + n * 4) % n)
			show_menu(menu, true)
		KEY_DOWN, KEY_S:
			menu.set_meta("sel", (int(menu.get_meta("sel")) + int(menu.get_meta("columns", n))) % n)
			show_menu(menu, true)
		KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
			pick_from_menu(menu, int(menu.get_meta("sel")))
		KEY_ESCAPE, KEY_I, KEY_K:
			show_menu(menu, false)


func pick_from_menu(menu: Control, i: int) -> void:
	var e: Dictionary = (menu.get_meta("entries") as Array)[i]
	show_menu(menu, false)
	(menu.get_meta("pick") as Callable).call(e.id)


func show_items(on: bool) -> void:
	show_menu(items_menu, on)


func choose_item(item: String) -> void:
	play_sfx(click_snd)
	if Rides.RIDES.has(item):
		summon_ride(item)
		return
	if play_mode:
		set_play(false)  # things like the couch go in the building lot
	set_place_item(item)


# ---------------------------------------------------------------- input + camera

func _unhandled_input(ev: InputEvent) -> void:
	if busy:
		return
	if ev is InputEventMouseButton:
		var mb := ev as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed and not play_mode:
			kb_aim = false
			update_hover()
			action()
		elif mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed and on_foot():
			combat.attack()
		elif mb.button_index == MOUSE_BUTTON_RIGHT:
			if mb.pressed:
				orbiting = true
				right_press_pos = mb.position
				right_moved = false
			else:
				orbiting = false
				if not right_moved and not play_mode:
					remove_hovered()
		elif mb.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and mb.pressed and mb.shift_pressed:
			tilt += 5.0 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else -5.0
			tilt = clampf(tilt, 0.0, 180.0) if hover_ground else wrapf(tilt, -180.0, 180.0)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			cam_dist = clampf(cam_dist * 0.9, 1.5, 40.0)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			cam_dist = clampf(cam_dist * 1.1, 1.5, 40.0)
	elif ev is InputEventMouseMotion:
		var mm := ev as InputEventMouseMotion
		if not orbiting and mm.relative.length() > 2.0 and key_script.is_empty():
			kb_aim = false
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
		var key := (ev as InputEventKey).keycode
		if picker.visible:
			picker_key(key)
			return
		for menu in [items_menu, smash_menu]:
			if menu.visible:
				menu_key(menu, key)
				return
		if key in [KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_Q, KEY_E, KEY_SPACE, KEY_F, KEY_G]:
			if not kb_aim:
				aim_pos = get_viewport().get_mouse_position()  # pick up where the mouse was
			kb_aim = true
		match key:
			KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_7, KEY_8:
				if not play_mode and key - KEY_1 < SHAPES.size():
					set_shape(SHAPES[key - KEY_1])
				elif on_foot():
					combat.equip(combat.ORDER[key - KEY_1])
					refresh_hud()
			KEY_F:
				if on_foot():
					combat.attack()
			KEY_C:
				if not play_mode:
					set_color((cur_color + 1) % COLORS.size())
			KEY_X:
				if not play_mode:
					set_erase(not erase_mode)
			KEY_Z:
				if not play_mode:
					undo()
			KEY_R:
				if driving:
					ride.right_side_up()
				else:
					flip()
			KEY_ENTER, KEY_KP_ENTER:
				if driving:
					exit_buggy()
				elif near_buggy():
					enter_buggy()
			KEY_SPACE:
				if not play_mode:
					action()
			KEY_BACKSPACE, KEY_DELETE:
				if not play_mode:
					remove_hovered()
			KEY_I:
				show_items(true)
			KEY_K:
				if not play_mode:
					show_menu(smash_menu, true)
			KEY_ESCAPE:
				if place_item != "":
					set_place_item("")
			KEY_TAB:
				set_play(not play_mode)
			KEY_P:
				show_picker(true)
			KEY_H:
				help_visible = not help_visible
				refresh_ui()


func _process(delta: float) -> void:
	var keys_live := not menu_open() and not busy
	if not play_mode and keys_live:
		# WASD moves the crosshair around the screen like a mouse pointer; pushing it
		# against the edge of the screen scrolls the view that way.
		var vs := get_viewport().get_visible_rect().size
		if aim_pos.x < 0.0:
			aim_pos = vs / 2.0
		var dir := Vector2.ZERO
		if Input.is_key_pressed(KEY_W):
			dir.y -= 1.0
		if Input.is_key_pressed(KEY_S):
			dir.y += 1.0
		if Input.is_key_pressed(KEY_A):
			dir.x -= 1.0
		if Input.is_key_pressed(KEY_D):
			dir.x += 1.0
		var lo := Vector2(vs.x * 0.06, vs.y * 0.08)
		var hi := Vector2(vs.x * 0.94, vs.y - 160.0)  # stay above the toolbar
		var want := aim_pos + dir * vs.y * 0.55 * delta
		aim_pos = want.clamp(lo, hi)
		var push := want - aim_pos  # how far past the edge we tried to go
		if kb_aim and push.length() > 0.0:
			var fwd := Vector3(-sin(cam_yaw), 0, -cos(cam_yaw))
			var right := Vector3(cos(cam_yaw), 0, -sin(cam_yaw))
			var move := right * signf(push.x) + fwd * -signf(push.y)
			cam_target += move.normalized() * clampf(cam_dist * 0.45, 1.5, 6.0) * delta
			var flat := Vector2(cam_target.x, cam_target.z).limit_length(BUILD_R + 4.0)
			cam_target.x = flat.x
			cam_target.z = flat.y
	if play_mode and hearts < MAX_HEARTS:
		heal_t += delta
		if heal_t > 6.0:
			heal_t = 0.0
			hearts += 1
			refresh_hud()
	if driving:
		# Chase cam: swing round behind the buggy (arrows still nudge it).
		var f: Vector3 = ride.global_basis.z
		var behind := atan2(-f.x, -f.z)
		if Vector2(f.x, f.z).length() > 0.3 and not (Input.is_key_pressed(KEY_LEFT) or Input.is_key_pressed(KEY_RIGHT)):
			cam_yaw = lerp_angle(cam_yaw, behind, 1.0 - exp(-2.5 * delta))
		cam_target = cam_target.lerp(ride.global_position + Vector3(0, 0.6, 0), 1.0 - exp(-12.0 * delta))
	elif play_mode:
		cam_target = cam_target.lerp(player.global_position + Vector3(0, 0.35, 0), 1.0 - exp(-10.0 * delta))
	if keys_live and not play_mode and place_item == "":
		var swing := 0.0
		if Input.is_key_pressed(KEY_F):
			swing += 1.0
		if Input.is_key_pressed(KEY_G):
			swing -= 1.0
		if swing != 0.0:
			tilt += swing * 45.0 * delta
			if hover_ground:
				tilt = clampf(tilt, 0.0, 180.0)
			else:
				tilt = wrapf(tilt, -180.0, 180.0)
	if keys_live:
		if Input.is_key_pressed(KEY_UP):
			cam_pitch = clampf(cam_pitch + 1.2 * delta, 0.05, 1.45)
		if Input.is_key_pressed(KEY_DOWN):
			cam_pitch = clampf(cam_pitch - 1.2 * delta, 0.05, 1.45)
		if Input.is_key_pressed(KEY_LEFT):
			cam_yaw += 1.8 * delta
		if Input.is_key_pressed(KEY_RIGHT):
			cam_yaw -= 1.8 * delta
		if Input.is_key_pressed(KEY_Q):
			cam_dist = clampf(cam_dist * (1.0 + 1.2 * delta), 1.5, 60.0 if play_mode else 40.0)
		if Input.is_key_pressed(KEY_E):
			cam_dist = clampf(cam_dist * (1.0 - 1.2 * delta), 1.5, 40.0)

	var off := Vector3(cos(cam_pitch) * sin(cam_yaw), sin(cam_pitch), cos(cam_pitch) * cos(cam_yaw)) * cam_dist
	if play_mode:
		# Out in the city: pull the camera in front of any wall that gets behind you.
		var q := PhysicsRayQueryParameters3D.create(cam_target, cam_target + off * 1.05, 2)
		var wall := get_world_3d().direct_space_state.intersect_ray(q)
		if not wall.is_empty():
			off = off.normalized() * maxf(cam_target.distance_to(wall.position) - 0.25, 0.4)
	cam.global_position = cam_target + off
	if shake > 0.0:
		cam.global_position += Vector3(randf_range(-1, 1), randf_range(-1, 1), randf_range(-1, 1)) * shake * 0.35
		shake = maxf(shake - delta * 1.8, 0.0)
	cam.look_at(cam_target, Vector3.UP)

	update_hover()
	highlight_item(hover_item if erase_mode and place_item == "" else null)
	var c: Color = (COLORS[cur_color] as Color).lightened(0.35)
	c.a = 0.45 + 0.2 * sin(Time.get_ticks_msec() / 160.0)
	ghost_mat.albedo_color = c
	if Time.get_ticks_msec() < flash_until:
		status_label.text = flash_text
	elif driving:
		var spec: Dictionary = Rides.RIDES[ride.kind]
		var how := "" if spec.type == "car" else ("Space climb  -  " if spec.get("style") != "rocket" else "Space blast off  -  ")
		status_label.text = "%s%s  -  G honk  -  Enter hop out" % [how, Rides.SPECIAL_TEXT[spec.special]]
	elif near_buggy():
		status_label.text = "Press Enter to hop in the %s!" % Rides.RIDES[nearest_ride().kind].name
	elif play_mode:
		status_label.text = ""
	elif place_item != "":
		status_label.text = "Move to pick a spot  -  R to turn  -  Space to put it down  -  Esc to cancel"
	elif ghost.visible and absf(tilt) > 0.01:
		status_label.text = ("Click! Corners stuck together" if ghost_snapped else "Tilted %+d°  -  F / G to keep tilting" % roundi(shown_tilt)) if ghost_ok else "Too close to another tile - tilt some more"
	elif ghost.visible and not hover_ground and candidates.size() > 1:
		status_label.text = "Way %d of %d  -  R to flip  -  F / G to tilt any angle" % [cand_index % candidates.size() + 1, candidates.size()]
	elif ghost.visible and hover_ground:
		status_label.text = "R to turn it  -  F / G to stand it up"
	elif ghost.visible:
		status_label.text = "F / G to tilt any angle"
	else:
		status_label.text = ""
	crosshair.visible = kb_aim and not play_mode and not menu_open() and not busy
	# Clear the screen for the Smash! show.
	(play_button.get_parent().get_parent() as Control).visible = not busy
	help_panel.visible = help_visible and not busy and not menu_open()
	crosshair.position = aim_pos
	crosshair.move_to_front()  # never hidden behind the controls card

	if shot_path != "":
		frame_count += 1
		if frame_count == shot_frame:
			for n in get_tree().get_nodes_in_group("npc"):
				print("npc ", n.kind, " ", n.state, " ", (n as Node3D).global_position)
			print("player ", player.global_position, " banner ", banner_label.text, " stars ", stars, " hearts ", hearts)
			print("shot: buggy at %s, %d tiles, %d fps, %d draw calls" % [buggy.global_position, tiles.size(), Engine.get_frames_per_second(), RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)])
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png(shot_path)
			get_tree().quit()


# ---------------------------------------------------------------- modes

func set_shape(s: String) -> void:
	cur_shape = s
	hover_key = ""
	set_place_item("")
	set_erase(false)


func set_color(i: int) -> void:
	cur_color = i
	set_erase(false)


func set_erase(on: bool) -> void:
	erase_mode = on
	hover_key = ""
	refresh_ui()


func set_play(on: bool) -> void:
	if driving and not on:
		exit_buggy()
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

	# Every button shows the key that does the same thing.
	for i in SHAPES.size():
		var b := add_button(row, str(i + 1), Vector2(76, 72), set_shape.bind(SHAPES[i]))
		b.icon = shape_icon(SHAPES[i])
		b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
		b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		shape_buttons[SHAPES[i]] = b
	row.add_child(VSeparator.new())
	for i in COLORS.size():
		var b := add_button(row, "C" if i == 0 else "", Vector2(46, 72), set_color.bind(i))
		b.add_theme_color_override("font_color", Color(0, 0, 0, 0.55))
		color_buttons.append(b)
	row.add_child(VSeparator.new())
	items_button = add_button(row, "I\nItems", Vector2(76, 72), func(): show_items(not items_menu.visible))
	smash_button = add_button(row, "K\nSmash!", Vector2(84, 72), func(): show_menu(smash_menu, not smash_menu.visible))
	flip_button = add_button(row, "R\nFlip", Vector2(76, 72), flip)
	erase_button = add_button(row, "X\nEraser", Vector2(84, 72), func(): set_erase(not erase_mode))
	undo_button = add_button(row, "Z\nUndo", Vector2(76, 72), undo)
	char_button = add_button(row, "P", Vector2(84, 72), func(): show_picker(not picker.visible))
	char_button.expand_icon = true
	play_button = add_button(row, "Tab\nPlay!", Vector2(96, 72), func(): set_play(not play_mode))
	build_picker(layer)
	var item_entries: Array = []
	for k in ITEMS:
		item_entries.append({"id": k, "name": ITEMS[k].name, "icon": ITEMS[k].icon})
	for k in Rides.RIDES:
		item_entries.append({"id": k, "name": Rides.RIDES[k].name, "icon": "res://assets/vehicles/%s.png" % k})
	items_menu = build_card_menu(layer, "Add something to your world", item_entries, choose_item)
	smash_menu = build_card_menu(layer, "How should we SMASH it?", [
		{"id": "giant", "name": "Giant Levi", "icon": "res://assets/giant/giant.png"},
		{"id": "ball", "name": "Wrecking Ball", "icon": "res://assets/crane/crane.png"},
	], func(kind): destroyer.start(kind))
	setup_help(layer)
	if DisplayServer.is_touchscreen_available() or "--touch" in OS.get_cmdline_user_args():
		var touch := Control.new()
		touch.set_script(preload("res://touch.gd"))
		touch.main = self
		layer.add_child(touch)
		help_visible = false  # the iPad has no keyboard: the keys card would just confuse

	# Explore mode: hearts + stars, a weapon bar and big announcements.
	hearts_label = Label.new()
	hearts_label.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	hearts_label.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	hearts_label.position = Vector2(-24, 14)
	hearts_label.add_theme_font_size_override("font_size", 34)
	hearts_label.add_theme_color_override("font_color", Color("ff5a6a"))
	hearts_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	hearts_label.add_theme_constant_override("outline_size", 8)
	layer.add_child(hearts_label)
	banner_label = Label.new()
	banner_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	banner_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	banner_label.position.y = 70
	banner_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	banner_label.add_theme_font_size_override("font_size", 38)
	banner_label.add_theme_color_override("font_color", Color("ffe066"))
	banner_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	banner_label.add_theme_constant_override("outline_size", 12)
	banner_label.modulate.a = 0.0
	banner_label.resized.connect(func(): banner_label.pivot_offset = banner_label.size / 2)
	layer.add_child(banner_label)
	var wpanel := PanelContainer.new()
	wpanel.add_theme_stylebox_override("panel", make_style(Color(0, 0, 0, 0.35), Color(0, 0, 0, 0), 0))
	wpanel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	wpanel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	wpanel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	wpanel.position.y -= 104
	layer.add_child(wpanel)
	weapon_bar = HBoxContainer.new()
	weapon_bar.add_theme_constant_override("separation", 8)
	wpanel.add_child(weapon_bar)
	for i in combat.ORDER.size():
		var w: String = combat.ORDER[i]
		var b := add_button(weapon_bar, str(i + 1), Vector2(70, 70), func(): combat.equip(w); refresh_hud())
		var icon := "res://assets/weapons/%s.png" % combat.MESH.get(w, "fists").to_lower()
		if ResourceLoader.exists(icon):
			b.icon = load(icon)
			b.expand_icon = true
			b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
			b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		else:
			b.text = "%d\n%s" % [i + 1, combat.WEAPONS[w].name.split(" ")[0]]
			b.add_theme_font_size_override("font_size", 15)
		b.tooltip_text = combat.WEAPONS[w].name
		weapon_buttons[w] = b
	var fight := add_button(weapon_bar, "F\nFight!", Vector2(84, 70), func(): combat.attack())
	style_button(fight, Color("c0392b"), false)

	# Aiming crosshair for keyboard building.
	crosshair = Control.new()
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(crosshair)
	for r in [[30, 4, Color(1, 1, 1, 0.9)], [8, 0, Color(1, 1, 1, 0.9)]]:
		var ring := Panel.new()
		var sb := make_style(Color(0, 0, 0, 0) if r[1] > 0 else r[2], r[2], r[1])
		sb.set_corner_radius_all(r[0])
		sb.shadow_color = Color(0, 0, 0, 0.35)
		sb.shadow_size = 3
		ring.add_theme_stylebox_override("panel", sb)
		ring.size = Vector2(r[0], r[0])
		ring.position = -ring.size / 2
		ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
		crosshair.add_child(ring)

	hint_label = Label.new()
	hint_label.position = Vector2(18, 14)
	hint_label.add_theme_font_size_override("font_size", 18)
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
	style_button(flip_button, Color("3a4a63"), false)
	style_button(smash_button, Color("c0392b"), false)
	style_button(items_button, Color("8a5a2b") if place_item != "" else Color("6b4a2b"), place_item != "")
	for b in shape_buttons.values() + color_buttons + [items_button, smash_button, flip_button, erase_button, undo_button]:
		(b as Button).visible = not play_mode
	for sep in (char_button.get_parent() as Node).find_children("*", "VSeparator", false, false):
		(sep as Control).visible = not play_mode
	char_button.icon = load("res://assets/portraits/%s.png" % player.character)
	style_button(char_button, Color("3a4a63"), false)
	play_button.text = "Tab\nBuild!" if play_mode else "Tab\nPlay!"
	items_button.visible = true
	refresh_hud()
	style_button(play_button, Color("2f9e55"), false)
	refresh_help()


func setup_help(layer: CanvasLayer) -> void:
	help_panel = PanelContainer.new()
	help_panel.add_theme_stylebox_override("panel", make_style(Color(0.04, 0.07, 0.14, 0.62), Color(0, 0, 0, 0), 0))
	help_panel.position = Vector2(14, 14)
	help_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(help_panel)
	help_grid = GridContainer.new()
	help_grid.columns = 2
	help_grid.add_theme_constant_override("h_separation", 12)
	help_grid.add_theme_constant_override("v_separation", 5)
	help_panel.add_child(help_grid)


func keycap(text: String) -> Control:
	var pc := PanelContainer.new()
	var sb := make_style(Color("f4f6fa"), Color("9aa7bd"), 0)
	sb.border_width_bottom = 3
	sb.set_corner_radius_all(6)
	sb.content_margin_left = 7
	sb.content_margin_right = 7
	sb.content_margin_top = 1
	sb.content_margin_bottom = 1
	pc.add_theme_stylebox_override("panel", sb)
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 16)
	l.add_theme_color_override("font_color", Color("1d2a40"))
	pc.add_child(l)
	return pc


func refresh_help() -> void:
	for c in help_grid.get_children():
		help_grid.remove_child(c)
		c.queue_free()
	var rows: Array
	if driving and Rides.RIDES[ride.kind].type == "fly":
		rows = [
			[["W", "S"], "Forward / back (plane: faster / slower)"], [["A", "D"], "Turn"],
			[["Space"], "Up!"], [["Shift"], "Down"], [["F"], "Special move"], [["G"], "Honk"],
			[["Left", "Right"], "Look around"], [["Q", "E"], "Zoom out / in"],
			[["Enter"], "Hop out"], [["I"], "Get a different vehicle"], [["H"], "Hide this help"],
		]
	elif driving:
		rows = [
			[["W"], "Gas"], [["S"], "Brake / back up"], [["A", "D"], "Steer"],
			[["Space"], "Handbrake"], [["F"], "Special move"], [["G"], "Honk"], [["R"], "Flip back over"],
			[["Left", "Right"], "Look around"], [["Q", "E"], "Zoom out / in"],
			[["Enter"], "Hop out"], [["H"], "Hide this help"],
		]
	elif play_mode:
		rows = [
			[["W", "A", "S", "D"], "Walk"], [["Space"], "Jump"],
			[["Left", "Right"], "Spin the camera"], [["Up", "Down"], "Look up / down"],
			[["Q", "E"], "Zoom out / in"], [["Enter"], "Drive the buggy (walk up to it)"],
			[["1", "-", "8"], "Pick a weapon"], [["F"], "Fight!"], [["I"], "Get a vehicle"],
			[["Tab"], "Back to building"], [["P"], "Pick your explorer"], [["H"], "Hide this help"],
		]
	else:
		rows = [
			[["W", "A", "S", "D"], "Move the aim"], [["Left", "Right"], "Spin the camera"],
			[["Up", "Down"], "Tilt the camera"], [["Q", "E"], "Zoom out / in"],
			[["Space"], "Place a tile"], [["R"], "Flip / turn the tile"], [["F", "G"], "Tilt the tile any angle"],
			[["Backspace"], "Remove a tile"], [["1", "2", "3", "4", "5"], "Pick a shape"],
			[["C"], "Change colour"], [["Z"], "Undo"],
			[["I"], "Add things (like our couch!)"], [["K"], "SMASH it!"],
			[["Tab"], "Go exploring!"], [["P"], "Pick your explorer"], [["H"], "Hide this help"],
		]
	for r in rows:
		var keys := HBoxContainer.new()
		keys.add_theme_constant_override("separation", 4)
		for k in r[0]:
			keys.add_child(keycap(k))
		help_grid.add_child(keys)
		var l := Label.new()
		l.text = r[1]
		l.add_theme_font_size_override("font_size", 17)
		help_grid.add_child(l)
	help_panel.visible = help_visible
	help_panel.reset_size.call_deferred()
	hint_label.text = "" if help_visible else "H: show controls"


func shape_icon(shape: String) -> ImageTexture:
	# Little filled silhouette of the tile for its toolbar button.
	var size := 40
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var v := shape_verts(shape)
	var poly := PackedVector2Array()
	var scale := 30.0 if shape == "big" else (17.0 if shape == "square" else 22.0)
	if shape == "tall":
		scale = 20.0
	for p in v:
		poly.append(Vector2(p.x, p.z) * scale + Vector2(size, size) / 2)
	var minp := Vector2(INF, INF)
	var maxp := Vector2(-INF, -INF)
	for q in poly:
		minp = minp.min(q)
		maxp = maxp.max(q)
	var shift := Vector2(size, size) / 2 - (minp + maxp) / 2  # centre the silhouette
	for i in poly.size():
		poly[i] += shift
	for y in size:
		for x in size:
			if Geometry2D.is_point_in_polygon(Vector2(x + 0.5, y + 0.5), poly):
				img.set_pixel(x, y, Color(0.85, 0.93, 1.0))
	return ImageTexture.create_from_image(img)


func run_key_script() -> void:
	# Testing aid: replays --keys=... as real key presses.
	for step in key_script:
		var down := InputEventKey.new()
		down.keycode = step[0]
		down.pressed = true
		Input.parse_input_event(down)
		for i in step[1]:
			await get_tree().process_frame
		var up := InputEventKey.new()
		up.keycode = step[0]
		up.pressed = false
		Input.parse_input_event(up)
		for i in 4:
			await get_tree().process_frame


func build_picker(layer: CanvasLayer) -> void:
	# Full-screen "Who do you want to be?" chooser with a big card per character.
	picker = ColorRect.new()
	(picker as ColorRect).color = Color(0.05, 0.08, 0.15, 0.55)
	picker.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	picker.mouse_filter = Control.MOUSE_FILTER_STOP
	picker.visible = false
	layer.add_child(picker)
	var centre := CenterContainer.new()
	centre.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	picker.add_child(centre)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 22)
	centre.add_child(col)
	var title := Label.new()
	title.text = "Who do you want to be?"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 44)
	title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.5))
	title.add_theme_constant_override("outline_size", 10)
	col.add_child(title)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 22)
	col.add_child(row)
	for c in CHARACTERS:
		var b := Button.new()
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(240, 300)
		b.icon = load("res://assets/portraits/%s.png" % c)
		b.expand_icon = true
		b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
		b.text = "%d  %s" % [CHARACTERS.find(c) + 1, CHARACTER_NAMES[c]]
		b.add_theme_font_size_override("font_size", 30)
		b.set_meta("character", c)
		b.pressed.connect(pick_character.bind(c))
		row.add_child(b)
	var how := Label.new()
	how.text = "Press 1, 2, 3 or 4  -  or use the arrow keys and Enter"
	how.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	how.add_theme_font_size_override("font_size", 22)
	how.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.5))
	how.add_theme_constant_override("outline_size", 6)
	col.add_child(how)
	var close := add_button(col, "Esc  Close", Vector2(170, 64), func(): show_picker(false))
	close.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	style_button(close, Color("3a4a63"), false)


func show_picker(on: bool) -> void:
	if on and not picker.visible:
		picker_sel = maxi(CHARACTERS.find(player.character), 0)
	picker.visible = on
	if on:
		for b in picker.find_children("*", "Button", true, false):
			if (b as Node).has_meta("character"):
				var sel: bool = CHARACTERS.find(b.get_meta("character")) == picker_sel
				style_button(b, Color("ffffff") if sel else Color("c9d3e3"), sel)
				(b as Button).get_theme_stylebox("normal").border_color = Color("ffb400") if sel else Color("9aa7bd")
				(b as Button).get_theme_stylebox("normal").set_border_width_all(8 if sel else 2)
				(b as Button).add_theme_color_override("font_color", Color("1d2a40"))
				(b as Button).add_theme_color_override("font_hover_color", Color("1d2a40"))


func picker_key(key: int) -> void:
	match key:
		KEY_1, KEY_2, KEY_3, KEY_4:
			pick_character(CHARACTERS[key - KEY_1])
		KEY_LEFT, KEY_A:
			picker_sel = (picker_sel + CHARACTERS.size() - 1) % CHARACTERS.size()
			show_picker(true)
		KEY_RIGHT, KEY_D:
			picker_sel = (picker_sel + 1) % CHARACTERS.size()
			show_picker(true)
		KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
			pick_character(CHARACTERS[picker_sel])
		KEY_ESCAPE, KEY_P:
			show_picker(false)


func pick_character(c: String) -> void:
	player.set_character(c)
	if driving:
		ride.set_driver(c)
	save_settings({"character": c})
	play_sfx(click_snd)
	show_picker(false)
	refresh_ui()


func load_settings() -> Dictionary:
	if not FileAccess.file_exists(SETTINGS_PATH):
		return {}
	var d = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS_PATH))
	return d if d is Dictionary else {}


func save_settings(d: Dictionary) -> void:
	if demo or no_save:
		return
	var f := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(d))


# ---------------------------------------------------------------- audio

func setup_audio() -> void:
	sfx = AudioStreamPlayer.new()
	add_child(sfx)
	click_snd = make_sound("click")
	pop_snd = make_sound("pop")
	crash_snd = make_sound("crash", 1.4)
	thud_snd = make_sound("thud", 0.9)


func make_sound(kind: String, dur := 0.14) -> AudioStreamWAV:
	var rate := 22050
	var n := int(rate * dur)
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
		elif kind == "crash":
			# Big plastic clatter: a thump plus lots of little rattles.
			s = sin(TAU * 55.0 * t) * exp(-t * 5.0) * 1.2 + (randf() * 2.0 - 1.0) * exp(-t * 3.5) * 0.7
			s += sin(TAU * (1400.0 + 900.0 * sin(t * 37.0)) * t) * exp(-t * 6.0) * 0.25 * (1.0 if fmod(t * 23.0, 1.0) < 0.3 else 0.0)
		elif kind == "thud":
			s = sin(TAU * (48.0 - 10.0 * t) * t) * exp(-t * 6.0) * 1.6 + (randf() * 2.0 - 1.0) * exp(-t * 25.0) * 0.3
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
	if demo or no_save:
		return
	var arr: Array = []
	for t in tiles:
		arr.append({"s": t.shape, "c": t.color, "x": xf_to_arr(t.xform)})
	var things: Array = []
	for it in items:
		things.append({"i": it.item, "x": xf_to_arr(it.xform)})
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"seed": city_seed, "tiles": arr, "items": things}))


func saved_seed() -> int:
	# The city this world was built in; a brand-new world rolls a new one.
	if FileAccess.file_exists(SAVE_PATH):
		var data = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
		if data is Dictionary and data.has("seed"):
			return int(data.seed)
		if data is Dictionary or data is Array:
			return 2026  # saved before cities had seeds: keep the city it was built in
	return randi_range(1, 999999)


static func xf_to_arr(x: Transform3D) -> Array:
	return [x.basis.x.x, x.basis.x.y, x.basis.x.z, x.basis.y.x, x.basis.y.y, x.basis.y.z,
		x.basis.z.x, x.basis.z.y, x.basis.z.z, x.origin.x, x.origin.y, x.origin.z]


static func arr_to_xf(a: Array) -> Transform3D:
	return Transform3D(Vector3(a[0], a[1], a[2]), Vector3(a[3], a[4], a[5]), Vector3(a[6], a[7], a[8]), Vector3(a[9], a[10], a[11]))


func load_world() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if data is Array:  # older saves were just the list of tiles
		data = {"tiles": data, "items": []}
	if not data is Dictionary:
		return
	for d in data.get("tiles", []):
		spawn_tile(d.s, int(d.c), arr_to_xf(d.x))
	for d in data.get("items", []):
		if ITEMS.has(d.i):
			spawn_item(d.i, arr_to_xf(d.x))


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


func build_photo_replica(at: Vector3) -> void:
	# Geoff's photo: a square stood up on the ground, a second square hinged off
	# its side at an open angle, and triangles standing on top of both.
	var keep := cur_shape
	cur_shape = "square"
	var g: Transform3D = ground_candidates(at, "square")[0]
	ground_hinge(g)
	var a := spawn_tile("square", 4, tilted(g, 90.0))
	# Side edge = the vertical one furthest along +X.
	var side := -1
	for i in 4:
		var d: Vector3 = a.verts[(i + 1) % 4] - a.verts[i]
		if absf(d.normalized().y) > 0.9 and (side < 0 or a.verts[i].x > a.verts[side].x):
			side = i
	var mid: Vector3 = (a.verts[side] + a.verts[(side + 1) % 4]) / 2
	var na: Vector3 = a.xform.basis.y
	var cands := edge_candidates(a, side, mid, na, "square")
	var flat_on: Transform3D = cands[0]
	for c in cands:  # the "straight on" option, in the same plane as tile a
		if absf((c as Transform3D).basis.y.normalized().dot(na)) > 0.99:
			flat_on = c
	hinge_pivot = a.verts[side]
	hinge_axis = (a.verts[(side + 1) % 4] - a.verts[side]).normalized()
	var b := spawn_tile("square", 4, tilted(flat_on, 60.0))
	cur_shape = "triangle"
	for t in [a, b]:
		var top := 0
		for i in 4:
			if t.verts[i].y + t.verts[(i + 1) % 4].y > t.verts[top].y + t.verts[(top + 1) % 4].y:
				top = i
		var m: Vector3 = (t.verts[top] + t.verts[(top + 1) % 4]) / 2
		var tc := edge_candidates(t, top, m, t.xform.basis.y, "triangle")
		for c in tc:  # stand it up in the same plane as the square
			if absf((c as Transform3D).basis.y.normalized().dot(t.xform.basis.y)) > 0.99:
				spawn_tile("triangle", 2, c)
				break
	cur_shape = keep


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
	# Right triangles: a wall of two (mirror pair) and a sloped roof on a floor square.
	var pad := spawn_tile("square", 6, ground_candidates(Vector3(-0.6, 0, 3.4), "square")[0])
	var c0 := edge_candidates(pad, 0, (pad.verts[0] + pad.verts[1]) / 2, Vector3.UP, "right")
	print("right-triangle options on a square edge: ", c0.size())
	var w1 := spawn_tile("right", 0, c0[0])
	var c1 := edge_candidates(w1, 2, (w1.verts[2] + w1.verts[0]) / 2, w1.xform.basis.y, "right")
	print("right-triangle options on a long edge: ", c1.size())
	spawn_tile("right", 1, c1[0])
	spawn_item("couch", Transform3D(Basis(Vector3.UP, PI / 4), Vector3(-6.0, 0, 4.0)))
	build_photo_replica(Vector3(4.6, 0, -4.4))
	print("demo tiles: ", tiles.size())
	cam_target = Vector3(0, 0.8, 0.5)
	cam_dist = 9.0
