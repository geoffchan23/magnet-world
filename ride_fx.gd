extends Node3D
## A ride's special move (F) and horn (G): the fire truck's water cannon, the
## police siren, the garbage truck scooping up junk, turbo boosts, the monster
## truck's big jump, the ice cream song, Santa dropping presents, the
## helicopter's spotlight. Lives inside the ride (vehicle.gd or flyer.gd).

const Rides := preload("res://rides.gd")

var main: Node3D
var ride: Node3D  # vehicle.gd / flyer.gd; has .driving, boost(), hop(), velocity_now()
var special := ""
var cool := 0.0
var holding := false
var horn_snd: AudioStreamPlayer3D
var loop_snd: AudioStreamPlayer3D  # siren / water / jingle
var siren_on := false
var siren_mats: Array = []  # [material, colour]
var siren_lights: Array = []
var spot: SpotLight3D
var water: CPUParticles3D
var nozzle: Node3D
var cannon: Node3D
var cannon_rest := Transform3D()
var flame: CPUParticles3D
var t := 0.0


func setup(r: Node3D, kind: String) -> void:
	ride = r
	special = Rides.RIDES[kind].special
	horn_snd = sound("horn", -6.0)
	match special:
		"hose":
			nozzle = ride.find_child("Nozzle", true, false) as Node3D
			cannon = ride.find_child("Cannon", true, false) as Node3D
			if cannon:
				cannon_rest = cannon.transform
				if nozzle:
					nozzle.reparent(cannon)  # so the nozzle swings with the cannon
			water = make_water()
			loop_snd = sound("water", -10.0)
		"siren":
			loop_snd = sound("siren", -8.0)
			for mi in ride.find_children("*", "MeshInstance3D", true, false):
				var m := (mi as MeshInstance3D).mesh
				for i in m.get_surface_count():
					var src := m.surface_get_material(i)
					if src and src.resource_name in ["SirenRed", "SirenBlue"]:
						var mat := (src as BaseMaterial3D).duplicate() as BaseMaterial3D
						(mi as MeshInstance3D).set_surface_override_material(i, mat)
						siren_mats.append([mat, Color("ff2020") if src.resource_name == "SirenRed" else Color("2060ff")])
			for c in [Color("ff2020"), Color("2060ff")]:
				var l := OmniLight3D.new()
				l.light_color = c
				l.omni_range = 4.0
				l.light_energy = 0.0
				l.position = Vector3(0.3 if c.r > 0.5 else -0.3, 1.1, 0)
				ride.add_child(l)
				siren_lights.append(l)
		"jingle":
			loop_snd = sound("jingle", -6.0)
		"spotlight":
			spot = SpotLight3D.new()
			spot.light_energy = 6.0
			spot.spot_range = 30.0
			spot.spot_angle = 18.0
			spot.light_color = Color("fff4d0")
			spot.rotation.x = -PI / 2 + 0.3
			spot.position = Vector3(0, -0.1, 0.6)
			spot.visible = false
			ride.add_child(spot)
		"boost":
			flame = make_flame()


func sound(kind: String, db: float) -> AudioStreamPlayer3D:
	var p := AudioStreamPlayer3D.new()
	p.stream = Rides.synth(kind)
	p.volume_db = db
	p.unit_size = 8.0
	ride.add_child.call_deferred(p)
	return p


func _physics_process(delta: float) -> void:
	t += delta
	cool -= delta
	var live: bool = ride.driving and not main.busy and not main.menu_open()
	var f_down := live and Input.is_key_pressed(KEY_F)
	var pressed := f_down and not holding
	holding = f_down
	if live and Input.is_key_pressed(KEY_G) and not horn_snd.playing:
		horn_snd.play()
		scare_people()
	match special:
		"hose":
			spray(f_down, delta)
		"siren":
			if pressed:
				siren_on = not siren_on
				if siren_on:
					loop_snd.play()
					scare_people()
				else:
					loop_snd.stop()
			var flip := fmod(t, 0.5) < 0.25
			for i in siren_mats.size():
				var m: BaseMaterial3D = siren_mats[i][0]
				m.emission_enabled = true
				m.emission = siren_mats[i][1]
				m.emission_energy_multiplier = (6.0 if ((i % 2 == 0) == flip) else 0.3) if siren_on else 0.5
			for i in siren_lights.size():
				(siren_lights[i] as OmniLight3D).light_energy = (3.0 if ((i == 0) == flip) else 0.0) if siren_on else 0.0
		"scoop":
			if pressed and cool <= 0.0:
				cool = 0.6
				scoop()
		"boost":
			if pressed and cool <= 0.0:
				cool = 2.5
				ride.boost()
				if flame:
					flame.restart()
					flame.emitting = true
		"jump":
			if pressed and cool <= 0.0:
				cool = 1.4
				ride.hop()
		"jingle":
			if pressed:
				if loop_snd.playing:
					loop_snd.stop()
				else:
					loop_snd.play()
					call_people("Ice cream!!")
		"presents":
			if pressed and cool <= 0.0:
				cool = 0.5
				drop_present()
		"loop":
			if pressed and cool <= 0.0:
				cool = 3.0
				ride.stunt()
		"spotlight":
			if pressed:
				spot.visible = not spot.visible
	if not ride.driving:
		if loop_snd and loop_snd.playing and special != "siren":
			loop_snd.stop()


# ---------------------------------------------------------------- the moves

func spray(on: bool, delta: float) -> void:
	# The water cannon follows where the truck is heading and lifts a bit.
	if cannon:
		cannon.transform = cannon_rest * Transform3D(Basis(Vector3.UP, sin(t * 2.0) * 0.15), Vector3.ZERO)
	water.emitting = on
	if on and not loop_snd.playing:
		loop_snd.play()
	elif not on and loop_snd.playing:
		loop_snd.stop()
	if not on:
		return
	var from: Vector3 = water.global_position
	var dir: Vector3 = nozzle.global_basis.z if nozzle else (ride.global_basis.z + Vector3(0, 0.25, 0)).normalized()
	# Where the water lands: a few steps along a falling arc.
	var p := from
	var v := dir * 11.0
	var space := get_world_3d().direct_space_state
	var land := p
	for i in 12:
		var nxt := p + v * 0.08
		v.y -= 14.0 * 0.08
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(p, nxt, 1 | 2 | 64 | 128))
		if not hit.is_empty():
			land = hit.position
			var c: Object = hit.collider
			if c.is_in_group("npc"):
				if c.friendly:
					if randf() < delta * 2.0:
						c.say("Splash!", 1.0, Color("aee8ff"))
					c.velocity += dir * 6.0 * delta
				elif randf() < delta * 2.0:
					c.take_hit(1, dir * 3.0)
			elif c is RigidBody3D:
				(c as RigidBody3D).apply_central_impulse(dir * 3.0 * delta)
			break
		p = nxt
		land = p
	main.encounters.spray(land, 1.2, delta)


func scoop() -> void:
	# Gobble up loose junk in front of the truck: +1 star each.
	var front: Vector3 = ride.global_position - ride.global_basis.z * 1.6
	var got := 0
	for b in main.combat.props_near(front, 1.6) + main.combat.props_near(ride.global_position + ride.global_basis.z * 1.6, 1.6):
		if is_instance_valid(b) and not (b as Node).is_queued_for_deletion():
			main.combat.sparkles((b as Node3D).global_position, Color("9fe870"), 10)
			(b as Node).queue_free()
			got += 1
	if got > 0:
		main.add_stars(got, front)
		main.flash("Munch! Scooped up %d piece%s of junk" % [got, "" if got == 1 else "s"])
	else:
		main.flash("Nothing to scoop - drive up to barrels, tyres or smashed tiles")


func drop_present() -> void:
	var box := RigidBody3D.new()
	box.collision_layer = 64
	box.collision_mask = 1 | 2 | 64
	box.mass = 0.3
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.3, 0.25, 0.3)
	var m := StandardMaterial3D.new()
	m.albedo_color = [Color("e53935"), Color("43a047"), Color("1e88e5"), Color("fdd835"), Color("8e24aa")][randi() % 5]
	m.roughness = 0.35
	bm.material = m
	mi.mesh = bm
	box.add_child(mi)
	var ribbon := MeshInstance3D.new()
	var rb := BoxMesh.new()
	rb.size = Vector3(0.32, 0.27, 0.06)
	var rm := StandardMaterial3D.new()
	rm.albedo_color = Color("fff3c0")
	rm.metallic = 0.6
	rm.roughness = 0.3
	rb.material = rm
	ribbon.mesh = rb
	box.add_child(ribbon)
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = bm.size
	cs.shape = shape
	box.add_child(cs)
	main.add_child(box)
	box.global_position = ride.global_position + Vector3(0, -0.1, 0) - ride.global_basis.z * 0.8
	box.linear_velocity = ride.velocity_now() * 0.6
	box.angular_velocity = Vector3(randf(), randf(), randf()) * 4.0
	get_tree().create_timer(20.0).timeout.connect(func(): if is_instance_valid(box): box.queue_free())
	for n in get_tree().get_nodes_in_group("npc"):
		if n.friendly and (n as Node3D).global_position.distance_to(box.global_position) < 8.0:
			n.say(["Thank you Santa!", "A present!", "Ho ho ho!"][randi() % 3], 2.0, Color("ffe066"))
			main.add_stars(1, (n as Node3D).global_position)
			break


func scare_people() -> void:
	for n in get_tree().get_nodes_in_group("npc"):
		if (n as Node3D).global_position.distance_to(ride.global_position) < 7.0:
			if n.friendly:
				n.say(["Beep beep!", "Whoa!", "Hi!"][randi() % 3], 1.0)
			else:
				n.flee_t = 3.0


func call_people(text: String) -> void:
	for n in get_tree().get_nodes_in_group("npc"):
		if n.friendly and (n as Node3D).global_position.distance_to(ride.global_position) < 18.0:
			n.home = ride.global_position
			n.target_pos = ride.global_position
			n.think_t = 4.0
			n.say(text, 2.0, Color("ffd0f0"))


# ---------------------------------------------------------------- effects

func make_water() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.amount = 90
	p.lifetime = 0.9
	p.emitting = false
	p.local_coords = false
	p.direction = Vector3(0, 0.25, 1)
	p.spread = 4.0
	p.initial_velocity_min = 10.0
	p.initial_velocity_max = 11.5
	p.gravity = Vector3(0, -14, 0)
	p.scale_amount_min = 0.6
	p.scale_amount_max = 1.6
	var q := QuadMesh.new()
	q.size = Vector2(0.12, 0.12)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.albedo_texture = Rides.soft_dot()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_color = Color(0.75, 0.9, 1.0, 0.75)
	q.material = m
	p.mesh = q
	var host: Node3D = nozzle if nozzle else ride
	host.add_child(p)
	if nozzle:
		p.direction = Vector3(0, 0, 1)  # the nozzle points where the water goes
	else:
		p.position = Vector3(0, 1.2, 0.8)
	return p


func make_flame() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.amount = 40
	p.lifetime = 0.35
	p.one_shot = true
	p.explosiveness = 0.0
	p.emitting = false
	p.direction = Vector3(0, 0, -1)
	p.spread = 12.0
	p.initial_velocity_min = 3.0
	p.initial_velocity_max = 5.0
	p.gravity = Vector3.ZERO
	var q := QuadMesh.new()
	q.size = Vector2(0.18, 0.18)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.albedo_texture = Rides.soft_dot()
	m.vertex_color_use_as_albedo = true
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	q.material = m
	p.mesh = q
	var g := Gradient.new()
	g.set_color(0, Color(0.6, 0.8, 1.0, 1.0))
	g.add_point(0.4, Color(1.0, 0.6, 0.2, 0.8))
	g.set_color(g.get_point_count() - 1, Color(0.3, 0.3, 0.3, 0.0))
	p.color_ramp = g
	var flame_at := ride.find_child("Flame", true, false) as Node3D
	if flame_at:
		flame_at.add_child(p)
	else:
		ride.add_child(p)
		p.position = Vector3(0, 0.4, -1.1)
	return p
