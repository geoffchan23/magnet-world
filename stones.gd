extends Node3D
## The six Infinity Stones, each hidden at its own site out in the city and
## guarded by Thanos or the Black Order and their army. Every site is a little
## building puzzle for the magnetic tiles:
##   Mind     - on the roof of Ultron's tower: build your way up
##   Space    - on a Chitauri platform floating in the air: build a tower to it
##   Reality  - on an island in a pool of goo: build a bridge over it
##   Power    - in a temple guarded by laser turrets: build walls to hide behind
##   Time     - on a balcony in Doctor Strange's Sanctum: go inside, bridge the gap
##   Soul     - on top of the Vormir mountain, guarded by Thanos: climb it with tiles
## A force field keeps vehicles (and flying!) out, so heroes go in on foot.
## Grab a stone and its power goes into your Infinity Gauntlet (powers.gd).

const City := preload("res://city.gd")
const NPC := preload("res://npc.gd")
const FIELD_R := 11.0  # force field radius around each site
const FIELD_LAYER := 256  # only vehicles bump into force fields
const NEAR := 45.0  # guards turn up when you get this close
const FAR := 75.0  # ...and go home when you're this far away

const ORDER := ["space", "mind", "reality", "power", "time", "soul"]
const STONES := {
	"space": {"name": "Space Stone", "color": Color("3f8cff"), "site": "float",
		"guards": ["cull_obsidian", "chitauri", "chitauri", "chitauri"],
		"hint": "The Space Stone floats on a Chitauri platform up in the air. Build a tower to reach it!"},
	"mind": {"name": "Mind Stone", "color": Color("ffd23f"), "site": "tower",
		"guards": ["corvus_glaive", "ultron_sentry", "ultron_sentry", "ultron_sentry"],
		"hint": "The Mind Stone is on the roof of Ultron's tower. Build your way up!"},
	"reality": {"name": "Reality Stone", "color": Color("ff2f3f"), "site": "pool",
		"guards": ["proxima_midnight", "hydra_agent", "hydra_agent", "hydra_agent"],
		"hint": "The Reality Stone sits on an island in a pool of goo. Build a bridge - don't touch the goo!"},
	"power": {"name": "Power Stone", "color": Color("a64dff"), "site": "vault",
		"guards": ["thanos", "outrider", "outrider"],
		"hint": "The Power Stone is in an old temple full of laser turrets. Build walls to hide behind!"},
	"time": {"name": "Time Stone", "color": Color("3fe07a"), "site": "sanctum",
		"guards": ["ebony_maw", "chitauri", "chitauri"],
		"hint": "The Time Stone is up on the balcony in Doctor Strange's Sanctum. Go inside and build a bridge!"},
	"soul": {"name": "Soul Stone", "color": Color("ff9a2f"), "site": "vormir",
		"guards": ["thanos", "outrider", "outrider", "outrider"],
		"hint": "The Soul Stone is on top of the Vormir mountain, and Thanos guards it. Build up the cliff!"},
}
# Where the stone sits on each site, from the middle of the block (pavement top).
const SPOT := {
	"tower": Vector3(0, 6.0, 0), "float": Vector3(0, 5.0, 0), "pool": Vector3(0, 0.35, 0),
	"vault": Vector3(0, 0.4, -2.4), "sanctum": Vector3(0.5, 4.0, -4.6), "vormir": Vector3(0, 7.0, 0),
}
const SITE_NAMES := {
	"tower": "Ultron's Tower", "float": "the Chitauri Platform", "pool": "the Goo Pool",
	"vault": "the Power Temple", "sanctum": "the Sanctum Sanctorum", "vormir": "Vormir",
}

var main: Node3D
var sites := {}  # stone -> {centre, root, stone_node, field, beam, guards, beaten, visited}
var collected: Array = []  # stone names you've got
var beaten: Array = []  # stones whose guard boss has been beaten
var kit := {}  # site piece name -> Node3D template (assets/sites)
var turrets: Array = []  # {head, muzzle, t, at}
var spin_t := 0.0


static func pick_blocks(seed_value: int) -> Dictionary:
	# Six city blocks out in the middle rings, spread all the way around the lot.
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value * 7 + 11
	var outer: Array = []
	for c in City.block_corners():
		var mid: Vector2 = c + Vector2(City.BLOCK / 2, City.BLOCK / 2)
		var ring := maxf(absf(mid.x), absf(mid.y))
		if ring > 40.0:  # not the first ring right next to the lot
			outer.append(c)
	outer.sort_custom(func(a, b): return (a as Vector2).angle() < (b as Vector2).angle())
	var out := {}
	var start := rng.randi_range(0, outer.size() - 1)
	var order := ORDER.duplicate()
	for i in order.size():
		var j := rng.randi_range(i, order.size() - 1)
		var tmp = order[i]
		order[i] = order[j]
		order[j] = tmp
	for i in order.size():
		var idx := (start + int(round(i * outer.size() / float(order.size()))) + rng.randi_range(0, 1)) % outer.size()
		out[order[i]] = outer[idx]
	return out


func build(blocks: Dictionary) -> void:
	load_kit()
	for stone in blocks:
		var c: Vector2 = blocks[stone]
		var centre := Vector3(c.x + City.BLOCK / 2, City.SLAB, c.y + City.BLOCK / 2)
		var root := Node3D.new()
		add_child(root)
		root.global_position = centre
		var site: String = STONES[stone].site
		sites[stone] = {"centre": centre, "root": root, "guards": [], "visited": false}
		call("site_" + site, root)
		if stone in collected:
			continue
		place_stone(stone)
		make_field(stone)


func blocks_used() -> Array:
	var out := []
	for s in sites:
		out.append(Vector2(sites[s].centre.x - City.BLOCK / 2, sites[s].centre.z - City.BLOCK / 2))
	return out


# ---------------------------------------------------------------- pieces

func load_kit() -> void:
	var path := "res://assets/sites/sites.glb"
	if ResourceLoader.exists(path):
		var scene: Node3D = (load(path) as PackedScene).instantiate()
		for n in scene.get_children():
			kit[(n as Node).name] = n
		add_child(scene)
		scene.visible = false
		scene.process_mode = Node.PROCESS_MODE_DISABLED
		for b in scene.find_children("*", "CollisionObject3D", true, false):
			(b as CollisionObject3D).collision_layer = 0


func piece(name: String, parent: Node3D, at := Vector3.ZERO, yaw := 0.0) -> Node3D:
	# A set piece from assets/sites (its collision becomes solid ground), or null.
	var src: Node3D = kit.get(name)
	if src == null and ResourceLoader.exists("res://assets/sites/%s.glb" % name.to_snake_case()):
		src = (load("res://assets/sites/%s.glb" % name.to_snake_case()) as PackedScene).instantiate()
		kit[name] = src
	if src == null:
		return null
	var n := src.duplicate() as Node3D
	n.transform = Transform3D(Basis(Vector3.UP, yaw), at)
	n.visible = true
	parent.add_child(n)
	for b in n.find_children("*", "CollisionObject3D", true, false):
		(b as CollisionObject3D).collision_layer = City.GROUND_LAYER
		(b as CollisionObject3D).collision_mask = 0
	# Same textured materials as the city kit (matched by material name).
	var meshes := n.find_children("*", "MeshInstance3D", true, false)
	if n is MeshInstance3D:
		meshes.append(n)
	for mi in meshes:
		var m := (mi as MeshInstance3D).mesh
		for i in m.get_surface_count():
			var sm := m.surface_get_material(i)
			if sm:
				(mi as MeshInstance3D).set_surface_override_material(i, main.city.kit_mat(sm))
	if n is CollisionObject3D:
		(n as CollisionObject3D).collision_layer = City.GROUND_LAYER
	return n


func block(parent: Node3D, size: Vector3, at: Vector3, col: Color, tex := "") -> void:
	# Stand-in box with collision (used until the set piece is modelled).
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	if tex != "":
		mi.material_override = main.city.tex_mat(tex, 0.5, col)
	else:
		var m := StandardMaterial3D.new()
		m.albedo_color = col
		m.roughness = 0.6
		mi.material_override = m
	mi.position = at + Vector3(0, size.y / 2, 0)
	parent.add_child(mi)
	var body := StaticBody3D.new()
	body.collision_layer = City.GROUND_LAYER
	body.collision_mask = 0
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	cs.shape = bs
	body.add_child(cs)
	body.position = mi.position
	parent.add_child(body)


# ---------------------------------------------------------------- sites

func site_tower(root: Node3D) -> void:
	if piece("UltronTower", root) == null:
		block(root, Vector3(4, 6, 4), Vector3.ZERO, Color("8a8f96"), "concrete")
		block(root, Vector3(4, 0.25, 0.8), Vector3(0, 2.75, 2.4), Color("6d7178"), "concrete")  # broken balcony
	scatter_rubble(root, 4)


func site_float(root: Node3D) -> void:
	var y: float = SPOT.float.y
	var plat := piece("HoverPlatform", root, Vector3(0, y, 0))
	if plat == null:
		block(root, Vector3(3, 0.3, 3), Vector3(0, y - 0.3, 0), Color("5b6a73"), "metal")
		plat = root
	# Glowing hover beams under the platform.
	for i in 4:
		var a := TAU * i / 4.0 + PI / 4
		var beam := MeshInstance3D.new()
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.12
		cyl.bottom_radius = 0.02
		cyl.height = y - 0.4
		cyl.material = glow_mat(Color("7ff0ff"), 0.35)
		beam.mesh = cyl
		beam.position = Vector3(cos(a) * 1.1, (y - 0.4) / 2, sin(a) * 1.1)
		root.add_child(beam)
	scatter_rubble(root, 5)


func site_pool(root: Node3D) -> void:
	if piece("GooPoolRim", root) == null:
		for i in 20:
			var a := TAU * i / 20.0
			var seg := Node3D.new()
			root.add_child(seg)
			seg.rotation.y = -a
			block(seg, Vector3(1.5, 0.35, 2.4), Vector3(7.75, 0, 0), Color("6a625a"), "concrete")
	if piece("GooIsland", root) == null:
		block(root, Vector3(2.6, 0.35, 2.6), Vector3.ZERO, Color("5a524a"), "concrete")
	# The goo itself: bubbling red Aether you mustn't touch.
	var goo := MeshInstance3D.new()
	var disc := CylinderMesh.new()
	disc.top_radius = 7.05
	disc.bottom_radius = 7.05
	disc.height = 0.05
	disc.radial_segments = 48
	goo.mesh = disc
	var sm := ShaderMaterial.new()
	sm.shader = load("res://shaders/goo.gdshader")
	goo.material_override = sm
	goo.position.y = 0.03
	root.add_child(goo)
	var bubbles := CPUParticles3D.new()
	bubbles.amount = 40
	bubbles.lifetime = 1.4
	bubbles.emission_shape = CPUParticles3D.EMISSION_SHAPE_RING
	bubbles.emission_ring_radius = 5.5
	bubbles.emission_ring_inner_radius = 2.0
	bubbles.emission_ring_height = 0.0
	bubbles.emission_ring_axis = Vector3.UP
	bubbles.direction = Vector3.UP
	bubbles.spread = 10.0
	bubbles.gravity = Vector3(0, 0.6, 0)
	bubbles.initial_velocity_min = 0.1
	bubbles.initial_velocity_max = 0.4
	bubbles.scale_amount_min = 0.5
	bubbles.scale_amount_max = 1.4
	var q := QuadMesh.new()
	q.size = Vector2(0.18, 0.18)
	q.material = glow_mat(Color("ff3a50"), 0.8, true)
	bubbles.mesh = q
	bubbles.position.y = 0.25
	root.add_child(bubbles)
	var light := OmniLight3D.new()
	light.light_color = Color("ff3040")
	light.light_energy = 1.5
	light.omni_range = 9.0
	light.position.y = 1.0
	root.add_child(light)


func site_vault(root: Node3D) -> void:
	if piece("VaultWalls", root) == null:
		var stone_col := Color("b9a98a")
		block(root, Vector3(12, 3, 0.6), Vector3(0, 0, -5.7), stone_col, "concrete")
		block(root, Vector3(0.6, 3, 12), Vector3(-5.7, 0, 0), stone_col, "concrete")
		block(root, Vector3(0.6, 3, 12), Vector3(5.7, 0, 0), stone_col, "concrete")
		block(root, Vector3(4.5, 3, 0.6), Vector3(-3.75, 0, 5.7), stone_col, "concrete")
		block(root, Vector3(4.5, 3, 0.6), Vector3(3.75, 0, 5.7), stone_col, "concrete")
		block(root, Vector3(2, 0.4, 2), Vector3(0, 0, -3.0), Color("8f8170"), "concrete")
	# Laser turrets either side of the stone, watching the door.
	for x: float in [-3.2, 3.2]:
		var t := piece("Turret", root, Vector3(x, 0, -2.0))
		var head: Node3D
		var muzzle: Node3D
		if t == null:
			block(root, Vector3(0.6, 0.8, 0.6), Vector3(x, 0, -2.0), Color("454b55"), "metal")
			head = Node3D.new()
			head.position = Vector3(x, 1.0, -2.0)
			root.add_child(head)
			var barrel := MeshInstance3D.new()
			var bm := BoxMesh.new()
			bm.size = Vector3(0.3, 0.3, 0.7)
			barrel.mesh = bm
			barrel.position.z = 0.3
			head.add_child(barrel)
			muzzle = Node3D.new()
			muzzle.position.z = 0.7
			head.add_child(muzzle)
		else:
			head = t.find_child("Head", true, false) as Node3D
			muzzle = t.find_child("Muzzle", true, false) as Node3D
			if head == null:
				head = t
			if muzzle == null:
				muzzle = head
		turrets.append({"head": head, "muzzle": muzzle, "t": randf() * 1.2, "stone": "power"})


func site_sanctum(root: Node3D) -> void:
	if piece("Sanctum", root) != null:
		# The roof is closed: warm lamps inside so it isn't dark.
		for p: Vector3 in [Vector3(0, 5.6, 0.6), Vector3(-3.5, 3.5, -2.5), Vector3(2.5, 3.0, 3.0)]:
			var l := OmniLight3D.new()
			l.light_color = Color("ffd8a0")
			l.light_energy = 1.6
			l.omni_range = 8.0
			l.position = p
			root.add_child(l)
		return
	# Stand-in: a hall with a door, stairs up the left wall to a landing, and a
	# balcony on the back wall with a gap in between.
	var wall := Color("8a4a3a")
	block(root, Vector3(12, 8, 0.4), Vector3(0, 0, -5.8), wall, "brick")
	block(root, Vector3(0.4, 8, 12), Vector3(-5.8, 0, 0), wall, "brick")
	block(root, Vector3(0.4, 8, 12), Vector3(5.8, 0, 0), wall, "brick")
	block(root, Vector3(5, 8, 0.4), Vector3(-3.5, 0, 5.8), wall, "brick")
	block(root, Vector3(5, 8, 0.4), Vector3(3.5, 0, 5.8), wall, "brick")
	block(root, Vector3(2, 5.6, 0.4), Vector3(0, 2.4, 5.8), wall, "brick")
	block(root, Vector3(12, 0.3, 12), Vector3(0, 8, 0), Color("4a3a30"))
	for i in 10:
		block(root, Vector3(1.4, 0.25 * (i + 1), 0.6), Vector3(-4.9, 0, 4.0 - i * 0.6), Color("6a4a32"), "plaster")
	block(root, Vector3(2.0, 2.5, 1.6), Vector3(-4.6, 0, -2.6), Color("6a4a32"), "plaster")  # landing
	block(root, Vector3(4.0, 0.3, 2.0), Vector3(2.0, 3.7, -4.6), Color("6a4a32"), "plaster")  # balcony


func site_vormir(root: Node3D) -> void:
	if piece("VormirSpire", root) == null:
		var rock := Color("5f5866")
		block(root, Vector3(3, 7, 3), Vector3.ZERO, rock, "concrete")
		block(root, Vector3(1.0, 0.4, 2.0), Vector3(-2.0, 2.1, 0), rock, "concrete")
		block(root, Vector3(1.0, 0.4, 2.0), Vector3(2.0, 4.1, 0), rock, "concrete")
	# Vormir's eerie mist.
	var mist := CPUParticles3D.new()
	mist.amount = 24
	mist.lifetime = 4.0
	mist.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	mist.emission_box_extents = Vector3(6, 0.2, 6)
	mist.gravity = Vector3(0, 0.05, 0)
	mist.initial_velocity_min = 0.05
	mist.initial_velocity_max = 0.2
	mist.scale_amount_min = 4.0
	mist.scale_amount_max = 7.0
	var q := QuadMesh.new()
	q.size = Vector2(0.6, 0.6)
	q.material = glow_mat(Color(0.75, 0.65, 0.9, 0.18), 0.18, true)
	mist.mesh = q
	mist.position.y = 0.3
	root.add_child(mist)


func scatter_rubble(root: Node3D, n: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = int(root.global_position.x * 13 + root.global_position.z * 7)
	for i in n:
		var a := rng.randf() * TAU
		var p: Vector3 = root.global_position + Vector3(cos(a), 0, sin(a)) * rng.randf_range(5.0, 8.5)
		main.city.prop(["Rubble_A", "Rubble_B", "Barrel"][rng.randi_range(0, 2)], p, rng.randf() * TAU)


# ---------------------------------------------------------------- stones, fields, beams

func glow_mat(col: Color, alpha := 1.0, particles := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color(col, alpha)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	if particles:
		m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		m.albedo_texture = main.Rides.soft_dot()
		m.vertex_color_use_as_albedo = true
	return m


func stone_model(stone: String) -> Node3D:
	var m: Node3D = main.combat.model_of("InfinityStone_" + stone.capitalize()) if main.combat.kit.has("InfinityStone_" + stone.capitalize()) else null
	if m == null:
		var mi := MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = 0.1
		sm.height = 0.26
		var mat := StandardMaterial3D.new()
		mat.albedo_color = STONES[stone].color
		mat.emission_enabled = true
		mat.emission = STONES[stone].color
		mat.emission_energy_multiplier = 3.0
		mat.metallic_specular = 1.0
		mat.roughness = 0.1
		sm.material = mat
		mi.mesh = sm
		m = Node3D.new()
		m.add_child(mi)
	return m


func place_stone(stone: String) -> void:
	var s: Dictionary = sites[stone]
	var site: String = STONES[stone].site
	var root: Node3D = s.root
	var at: Vector3 = SPOT[site]
	var ped: Node3D = main.combat.model_of("Pedestal") if main.combat.kit.has("Pedestal") else null
	var top := 0.7
	if ped:
		root.add_child(ped)
		ped.position = at
		for mi in ped.find_children("*", "MeshInstance3D", true, false):
			var m := (mi as MeshInstance3D).mesh
			for i in m.get_surface_count():
				var sm := m.surface_get_material(i)
				if sm and sm.resource_name == "Glow":
					var g := (sm as StandardMaterial3D).duplicate() as StandardMaterial3D
					g.emission_enabled = true
					g.emission = STONES[stone].color
					g.emission_energy_multiplier = 2.5
					(mi as MeshInstance3D).set_surface_override_material(i, g)
	else:
		block(root, Vector3(0.6, 0.7, 0.6), at, Color("40424a"), "metal")
	var holder := Node3D.new()
	holder.position = at + Vector3(0, top + 0.35, 0)
	root.add_child(holder)
	var gem := stone_model(stone)
	gem.scale = Vector3.ONE * 1.6
	holder.add_child(gem)
	var light := OmniLight3D.new()
	light.light_color = STONES[stone].color
	light.light_energy = 2.5
	light.omni_range = 4.0
	holder.add_child(light)
	var sparkle := CPUParticles3D.new()
	sparkle.amount = 20
	sparkle.lifetime = 1.2
	sparkle.emission_shape = CPUParticles3D.EMISSION_SHAPE_SPHERE
	sparkle.emission_sphere_radius = 0.35
	sparkle.gravity = Vector3(0, 0.8, 0)
	sparkle.initial_velocity_max = 0.2
	var q := QuadMesh.new()
	q.size = Vector2(0.06, 0.06)
	q.material = glow_mat(STONES[stone].color, 1.0, true)
	sparkle.mesh = q
	holder.add_child(sparkle)
	# A beam of light up into the sky, so you can see where it is from far away.
	var beam := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.5
	cyl.bottom_radius = 0.15
	cyl.height = 80.0
	cyl.cap_top = false
	cyl.cap_bottom = false
	cyl.material = glow_mat(STONES[stone].color, 0.22)
	beam.mesh = cyl
	beam.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	beam.position = holder.position + Vector3(0, 40.4, 0)
	root.add_child(beam)
	s.stone_node = holder
	s.beam = beam


func make_field(stone: String) -> void:
	# A shimmering dome: vehicles and flyers bounce off it; heroes on foot walk through.
	var s: Dictionary = sites[stone]
	var dome := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = FIELD_R
	sm.height = FIELD_R * 2
	sm.radial_segments = 48
	sm.rings = 24
	dome.mesh = sm
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/force_field.gdshader")
	mat.set_shader_parameter("tint", STONES[stone].color.lerp(Color("b070ff"), 0.5))
	dome.material_override = mat
	dome.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	(s.root as Node3D).add_child(dome)
	var body := StaticBody3D.new()
	body.collision_layer = FIELD_LAYER
	body.collision_mask = 0
	var cs := CollisionShape3D.new()
	var sh := SphereShape3D.new()
	sh.radius = FIELD_R
	cs.shape = sh
	body.add_child(cs)
	(s.root as Node3D).add_child(body)
	s.field = [dome, body]


func inside_field(p: Vector3, margin := 0.0) -> bool:
	for stone in sites:
		var s: Dictionary = sites[stone]
		if s.has("field") and (s.centre as Vector3).distance_to(p) < FIELD_R + margin:
			return true
	return false


# ---------------------------------------------------------------- each frame

func _physics_process(delta: float) -> void:
	if sites.is_empty():
		return
	spin_t += delta
	var here: Vector3 = main.player_body().global_position
	for stone in sites:
		var s: Dictionary = sites[stone]
		var c: Vector3 = s.centre
		var d := Vector2(here.x - c.x, here.z - c.z).length()
		if s.has("stone_node"):
			var h: Node3D = s.stone_node
			h.rotation.y = spin_t * 1.4
			(h.get_child(0) as Node3D).position.y = sin(spin_t * 2.0) * 0.06
			if main.on_foot() and (h.global_position - Vector3(0, 0.2, 0)).distance_to(main.player.global_position) < 0.75:
				collect(stone)
				continue
		# Guards turn up as you come close.
		if stone not in collected and d < NEAR and (s.guards as Array).is_empty() and main.play_mode:
			spawn_guards(stone)
		elif d > FAR and not (s.guards as Array).is_empty():
			for g in s.guards:
				if is_instance_valid(g):
					g.queue_free()
			s.guards = []
		if d < FIELD_R + 4.0 and not s.visited and main.play_mode and stone not in collected:
			s.visited = true
			var where: String = SITE_NAMES[STONES[stone].site]
			main.banner("%s! %s" % [where[0].to_upper() + where.substr(1), STONES[stone].hint])
	# The goo pool: touch it and you're back on the edge.
	var pool = site_of("pool")
	if pool and main.on_foot():
		var c: Vector3 = pool.centre
		var off := Vector2(here.x - c.x, here.z - c.z)
		if off.length() < 7.0 and off.length() > 1.5 and here.y < c.y + 0.25:
			var out := off.normalized() if off.length() > 0.01 else Vector2.RIGHT
			main.player.global_position = c + Vector3(out.x, 0, out.y) * 9.2 + Vector3(0, 0.6, 0)
			main.player.velocity = Vector3.ZERO
			main.combat.sparkles(here + Vector3(0, 0.2, 0), Color("ff3a50"), 30, 0.8)
			main.play_sfx(main.thud_snd)
			main.banner("Yuck, goo! Build a bridge to get across.")
	for t in turrets:
		aim_turret(t, delta, here)


func site_of(site: String):
	for stone in sites:
		if STONES[stone].site == site:
			return sites[stone]
	return null


func aim_turret(t: Dictionary, delta: float, here: Vector3) -> void:
	if t.stone in collected:
		return
	var head: Node3D = t.head
	var muzzle: Node3D = t.muzzle
	var target := here + Vector3(0, 0.25, 0)
	if head.global_position.distance_to(target) > 13.0 or not main.on_foot():
		return
	var flat := target - head.global_position
	head.global_rotation.y = lerp_angle(head.global_rotation.y, atan2(flat.x, flat.z), 4.0 * delta)
	t.t -= delta
	if t.t > 0.0:
		return
	t.t = 1.3
	# Only shoots if it can see you (your tiles make great cover!).
	var q := PhysicsRayQueryParameters3D.create(muzzle.global_position, target, 1 | 2)
	if not get_world_3d().direct_space_state.intersect_ray(q).is_empty():
		return
	main.combat.enemy_shot(muzzle.global_position, target, Color("c070ff"))


func spawn_guards(stone: String) -> void:
	var s: Dictionary = sites[stone]
	var c: Vector3 = s.centre
	var list: Array = STONES[stone].guards
	for i in list.size():
		var kind: String = list[i]
		if NPC.KINDS[kind].get("boss", false) and stone in beaten:
			continue  # already sent packing
		# The boss waits by the stone; the others patrol around the site.
		var a := TAU * i / list.size() + 0.4
		var r := 3.5 if i == 0 else 6.0
		var at := c + Vector3(cos(a), 0, sin(a)) * r
		if STONES[stone].site == "sanctum":
			at = c + Vector3(randf_range(-3, 3), 0, randf_range(-2, 3))
		elif STONES[stone].site == "pool":
			at = c + Vector3(cos(a), 0, sin(a)) * 9.0
		var n: Node3D = main.encounters.spawn(kind, at + Vector3(0, 0.4, 0))
		n.set_meta("scenario", true)
		n.home = at
		n.guard = true
		if n.info.get("boss", false):
			n.defeated.connect(func(_npc): boss_beaten(stone))
		(s.guards as Array).append(n)


func boss_beaten(stone: String) -> void:
	if stone not in beaten:
		beaten.append(stone)
	main.banner("You beat %s! Now grab the %s!" % [NPC.KINDS[STONES[stone].guards[0]].name, STONES[stone].name])
	main.save_world()


func collect(stone: String) -> void:
	var s: Dictionary = sites[stone]
	collected.append(stone)
	var at: Vector3 = (s.stone_node as Node3D).global_position
	main.combat.sparkles(at, STONES[stone].color, 60, 1.4)
	main.combat.sparkles(at, Color.WHITE, 30, 1.0)
	main.shake = 0.5
	(s.stone_node as Node).queue_free()
	(s.beam as Node).queue_free()
	s.erase("stone_node")
	s.erase("beam")
	if s.has("field"):
		for n in s.field:
			(n as Node).queue_free()
		s.erase("field")
	main.add_stars(10, at)
	main.powers.got(stone)
	if collected.size() == ORDER.size():
		main.banner("ALL SIX INFINITY STONES! Pick the Snap and press F...")
	else:
		main.banner("You got the %s! (%d of 6)  %s" % [STONES[stone].name, collected.size(), main.powers.POWER_TEXT[stone]])
	main.save_world()


func hint(from: Vector3) -> String:
	# Nick Fury's tip: which way to the nearest stone you haven't got yet.
	var best := ""
	var best_d := INF
	for stone in sites:
		if stone in collected:
			continue
		var d := from.distance_to(sites[stone].centre)
		if d < best_d:
			best = stone
			best_d = d
	if best == "":
		return "You've got all six stones, hero!"
	var to: Vector3 = (sites[best].centre as Vector3) - from
	var dirs := ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
	var ang := fposmod(atan2(to.x, -to.z), TAU)
	var word: String = dirs[int(round(ang / (TAU / 8))) % 8]
	return "The %s is %s of here - follow the %s light!" % [STONES[best].name, word, color_word(best)]


static func color_word(stone: String) -> String:
	return {"space": "blue", "mind": "yellow", "reality": "red", "power": "purple", "time": "green", "soul": "orange"}[stone]


func blocks_build(p: Vector3) -> bool:
	# No building on the goo (it would just sink).
	var pool = site_of("pool")
	if pool == null:
		return false
	var off := Vector2(p.x - pool.centre.x, p.z - pool.centre.z).length()
	return off < 7.0 and off > 1.6 and p.y < pool.centre.y + 0.3


func save_state() -> Dictionary:
	return {"collected": collected, "beaten": beaten}


func load_state(d: Dictionary) -> void:
	collected = d.get("collected", [])
	beaten = d.get("beaten", [])
