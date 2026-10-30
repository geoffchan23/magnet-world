extends Node3D
## Keeps the city alive while you explore: New Yorkers, S.H.I.E.L.D. agents and
## Thanos's invaders out on the streets near you, plus a random scenario every
## so often (a Chitauri ambush, someone who needs rescuing, an Outrider pack, a
## burning car for the fire truck, a S.H.I.E.L.D. supply drop...). Things far
## behind you are cleared away again.

const Rides := preload("res://rides.gd")
const NPC := preload("res://npc.gd")
const KEEP := 10  # wandering folk to keep around you
const NEAR := 16.0  # spawn at least this far away (out of the way)...
const FAR := 34.0  # ...and no further than this
const GONE := 60.0  # clear things up past this distance
const LOT := 16.0  # never inside the building lot

const STREET_LIFE := ["civilian", "civilian", "civilian", "shield_agent", "nick_fury", "lucky", "outrider", "outrider", "symbiote", "chitauri", "hydra_agent", "spider_drone", "ultron_sentry"]

var main: Node3D
var rng := RandomNumberGenerator.new()
var next_scenario := 20.0
var force_next := ""  # testing: --scenario=kind starts that one right away
var scenario: Dictionary = {}  # the one that's running: {kind, at, foes, friend, ...}
var fires: Array = []  # burning wrecks: {node, at, hp}
var drops: Array = []  # supply crates


func _ready() -> void:
	rng.randomize()


func _physics_process(delta: float) -> void:
	if not main.play_mode or main.busy:
		return
	var here: Vector3 = main.player_body().global_position
	# Tidy up.
	for n in get_tree().get_nodes_in_group("npc"):
		if (n as Node3D).global_position.distance_to(here) > GONE and not (n as Node).has_meta("scenario"):
			n.queue_free()
	# Top up the street life.
	var count := get_tree().get_nodes_in_group("npc").size()
	if count < KEEP and Engine.get_physics_frames() % 15 == 0:
		var at = spot_near(here, NEAR, FAR)
		if at != null:
			spawn(STREET_LIFE[rng.randi_range(0, STREET_LIFE.size() - 1)], at)
	next_scenario -= delta
	if scenario.is_empty() and (next_scenario <= 0.0 or force_next != ""):
		start_scenario(force_next)
		force_next = ""
	elif not scenario.is_empty():
		check_scenario()
	for f in fires.duplicate():
		if not is_instance_valid(f.node):
			fires.erase(f)
	for d in drops.duplicate():
		if not is_instance_valid(d):
			drops.erase(d)
		elif (d as Node3D).global_position.distance_to(here) < 0.9 and main.on_foot():
			open_drop(d)


func spawn(kind: String, at: Vector3) -> CharacterBody3D:
	var n := CharacterBody3D.new()
	n.set_script(NPC)
	n.main = main
	n.add_to_group("npc")
	add_child(n)
	n.setup(kind, at)
	return n


func spot_near(around: Vector3, lo: float, hi: float):
	# Somewhere open on the ground (a road, pavement or the wasteland).
	var space := get_world_3d().direct_space_state
	for i in 40:
		var a := rng.randf() * TAU
		var r := rng.randf_range(lo, hi)
		var p := Vector3(around.x + cos(a) * r, 0, around.z + sin(a) * r)
		if absf(p.x) < LOT and absf(p.z) < LOT:
			continue
		var from := p + Vector3(0, 30, 0)
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(from, p + Vector3(0, -2, 0), 2 | 1))
		if not hit.is_empty() and (hit.position as Vector3).y < 0.3:
			return hit.position + Vector3(0, 0.05, 0)
	return null


# ---------------------------------------------------------------- scenarios

func start_scenario(force := "") -> void:
	var here: Vector3 = main.player_body().global_position
	var at = spot_near(here, 4.0, 7.0) if force != "" else spot_near(here, 12.0, 22.0)
	if at == null:
		next_scenario = 5.0
		return
	var kinds := ["ambush", "rescue", "nest", "robots", "slimes", "supply", "hydra"]
	if main.driving:
		kinds.append("fire")
		kinds.append("fire")
	var kind: String = force if force != "" else kinds[rng.randi_range(0, kinds.size() - 1)]
	scenario = {"kind": kind, "at": at, "foes": []}
	match kind:
		"ambush":
			main.banner("Chitauri ambush! Avengers, assemble!")
			for i in 3:
				scenario.foes.append(spawn("chitauri", at + jitter(1.5)))
		"rescue":
			main.banner("Someone's in trouble - help them!")
			scenario.friend = spawn(["civilian", "shield_agent", "civilian"][rng.randi_range(0, 2)], at)
			scenario.friend.set_meta("scenario", true)
			for i in 3:
				var a := TAU * i / 3.0
				scenario.foes.append(spawn(["ultron_sentry", "outrider", "chitauri"][rng.randi_range(0, 2)], at + Vector3(cos(a), 0, sin(a)) * 1.6))
		"nest":
			main.banner("An Outrider pack! Here they come!")
			for i in 5:
				scenario.foes.append(spawn("outrider", at + jitter(2.0)))
		"robots":
			main.banner("Ultron's robots are on patrol!")
			scenario.foes.append(spawn("ultron_sentry", at))
			scenario.foes.append(spawn("spider_drone", at + jitter(1.5)))
			scenario.foes.append(spawn("spider_drone", at + jitter(1.5)))
		"slimes":
			main.banner("Symbiotes! Boing boing!")
			for i in 6:
				scenario.foes.append(spawn("symbiote", at + jitter(2.0)))
		"hydra":
			main.banner("Hydra agents are up to no good!")
			for i in 3:
				scenario.foes.append(spawn("hydra_agent", at + jitter(1.8)))
		"supply":
			main.banner("A S.H.I.E.L.D. supply drop is coming down! Go grab it!")
			drop_crate(at)
		"fire":
			main.banner("A car is on fire! Get the fire truck (Items) and spray it with F!")
			start_fire(at)
	for f in scenario.foes:
		(f as Node).set_meta("scenario", true)


func check_scenario() -> void:
	var foes_left := 0
	for f in scenario.foes:
		if is_instance_valid(f) and f.state != "dead":
			foes_left += 1
	var here: Vector3 = main.player_body().global_position
	var done := false
	match scenario.kind:
		"supply":
			done = drops.is_empty()
		"fire":
			done = fires.is_empty()
			if done:
				main.banner("Fire's out! You're a hero!")
				main.add_stars(3, scenario.at)
		_:
			if foes_left == 0 and not scenario.foes.is_empty():
				done = true
				if scenario.has("friend") and is_instance_valid(scenario.friend):
					scenario.friend.say("Thank you!!", 3.0, Color("ffe066"))
					main.banner("You saved them!")
					main.add_stars(3, scenario.at)
				else:
					main.banner("You did it!")
					main.add_stars(2, scenario.at)
	# Wandered off and left it? Let it go.
	if not done and here.distance_to(scenario.at) > GONE:
		done = true
	if done:
		for f in scenario.foes:
			if is_instance_valid(f):
				(f as Node).remove_meta("scenario")
		if scenario.has("friend") and is_instance_valid(scenario.friend):
			(scenario.friend as Node).remove_meta("scenario")
		scenario = {}
		next_scenario = rng.randf_range(25.0, 45.0)


func jitter(r: float) -> Vector3:
	return Vector3(rng.randf_range(-r, r), 0, rng.randf_range(-r, r))


func drop_crate(at: Vector3) -> void:
	# A crate floats down under a parachute; walk into it to open it.
	var crate := Node3D.new()
	var box := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.5, 0.4, 0.5)
	var m := StandardMaterial3D.new()
	m.albedo_color = Color("6f8a3a")
	m.roughness = 0.7
	bm.material = m
	box.mesh = bm
	box.position.y = 0.2
	crate.add_child(box)
	var chute := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.7
	sm.height = 0.7
	sm.is_hemisphere = true
	var cm := StandardMaterial3D.new()
	cm.albedo_color = Color("f0f0f0")
	cm.cull_mode = BaseMaterial3D.CULL_DISABLED
	sm.material = cm
	chute.mesh = sm
	chute.name = "Chute"
	chute.position.y = 1.6
	crate.add_child(chute)
	var glow := OmniLight3D.new()
	glow.light_color = Color("ffe066")
	glow.light_energy = 1.5
	glow.omni_range = 2.0
	glow.position.y = 0.6
	crate.add_child(glow)
	add_child(crate)
	crate.global_position = at + Vector3(0, 14, 0)
	var tw := create_tween()
	tw.tween_property(crate, "global_position", at, 5.0)
	tw.tween_callback(func(): if is_instance_valid(chute): chute.queue_free())
	drops.append(crate)


func open_drop(crate: Node3D) -> void:
	drops.erase(crate)
	main.combat.sparkles(crate.global_position + Vector3(0, 0.3, 0), Color("ffe066"), 30)
	main.add_stars(3, crate.global_position)
	main.banner("Supply crate! +3 stars")
	crate.queue_free()


func start_fire(at: Vector3) -> void:
	var node := Node3D.new()
	add_child(node)
	node.global_position = at
	var car := MeshInstance3D.new()
	car.mesh = main.city.piece("Car_Wreck_A")
	node.add_child(car)
	var fire := CPUParticles3D.new()
	fire.amount = 60
	fire.lifetime = 0.9
	fire.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	fire.emission_box_extents = Vector3(0.35, 0.1, 0.8)
	fire.direction = Vector3.UP
	fire.spread = 15.0
	fire.gravity = Vector3(0, 2.5, 0)
	fire.initial_velocity_min = 0.5
	fire.initial_velocity_max = 1.4
	fire.scale_amount_min = 0.6
	fire.scale_amount_max = 1.4
	var q := QuadMesh.new()
	q.size = Vector2(0.35, 0.35)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.albedo_texture = Rides.soft_dot()
	m.vertex_color_use_as_albedo = true
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	q.material = m
	fire.mesh = q
	var g := Gradient.new()
	g.set_color(0, Color(1.0, 0.85, 0.3, 0.9))
	g.add_point(0.5, Color(1.0, 0.35, 0.05, 0.7))
	g.set_color(g.get_point_count() - 1, Color(0.2, 0.2, 0.2, 0.0))
	fire.color_ramp = g
	fire.position.y = 0.5
	node.add_child(fire)
	var light := OmniLight3D.new()
	light.light_color = Color("ff8a30")
	light.light_energy = 3.0
	light.omni_range = 4.0
	light.position.y = 1.0
	node.add_child(light)
	fires.append({"node": node, "at": at, "hp": 3.0, "fire": fire, "light": light})


func spray(at: Vector3, radius: float, delta: float) -> void:
	# Called by the fire truck's water cannon.
	for f in fires.duplicate():
		if (f.at as Vector3).distance_to(at) < radius + 1.0:
			f.hp -= delta
			var k := clampf(f.hp / 3.0, 0.0, 1.0)
			(f.fire as CPUParticles3D).scale_amount_max = 1.4 * k
			(f.light as OmniLight3D).light_energy = 3.0 * k
			if f.hp <= 0.0:
				(f.fire as CPUParticles3D).emitting = false
				(f.light as OmniLight3D).visible = false
				main.combat.sparkles(f.at + Vector3(0, 0.6, 0), Color("cfefff"), 30)
				fires.erase(f)
