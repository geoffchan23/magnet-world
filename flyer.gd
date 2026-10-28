extends CharacterBody3D
## Things that fly: Santa's sleigh, the plane, the helicopter, the rocket ship,
## the hoverboard and the jetpack (see rides.gd). Arcade flying, so it's easy:
##
##  hover (sleigh, helicopter, hoverboard, jetpack): W / S forward and back,
##      A / D turn, Space up, Shift down.
##  plane: W / S faster and slower, A / D bank and turn, Space climb, Shift dive.
##      Below take-off speed it rolls along the ground.
##  rocket: Space blasts off, W / S tip forward and back, A / D turn.
##
## F special move, G horn, Enter hops out (lands first if you're up high).

const Rides := preload("res://rides.gd")
const LAYER := 32

var main: Node3D
var kind := ""
var spec: Dictionary
var style := "hover"
var fx: Node3D
var driving := false
var driver: Node3D
var seat := Transform3D(Basis(), Vector3(0, 0.35, 0))
var yaw := 0.0
var bank := 0.0
var pitch := 0.0
var speed := 0.0  # plane: forward airspeed
var lift := 0.0  # rocket: how hard it's blasting
var loop_t := 0.0  # plane stunt
var boost_t := 0.0
var spin_parts: Array = []  # [node, axis, rest]
var deer: Array = []  # sleigh: reindeer parts to gallop {node, rest, phase}
var flaps := {}  # plane control surfaces: name -> rest transform
var turn_now := 0.0
var exhaust: CPUParticles3D  # rocket fire
var model_root: Node3D
var engine_snd: AudioStreamPlayer3D
var spawn_xf := Transform3D()
var t := 0.0


func setup(at: Transform3D, k: String) -> void:
	kind = k
	spec = Rides.RIDES[k]
	style = spec.style
	spawn_xf = at
	collision_layer = LAYER
	collision_mask = 1 | 2 | LAYER
	model_root = Node3D.new()
	add_child(model_root)
	var path := Rides.model_path(k)
	var model: Node3D = (load(path) as PackedScene).instantiate() if ResourceLoader.exists(path) else stand_in()
	for n in model.get_children():
		var xf: Transform3D = (n as Node3D).transform
		model.remove_child(n)
		model_root.add_child(n)
		(n as Node3D).transform = xf
	model.queue_free()
	var seat_node := model_root.find_child("Seat", true, false) as Node3D
	if seat_node:
		# Seats mark the cushion top (figures stand on their origin); boards mark the deck.
		seat = Transform3D(Basis(), seat_node.position + (Vector3.ZERO if spec.get("low", false) else Vector3(0, -0.094, 0)))
	for n in ["Propeller", "Rotor", "TailRotor"]:
		var p := model_root.find_child(n, true, false) as Node3D
		if p:
			var axis := Vector3.FORWARD if n == "Propeller" else (Vector3.RIGHT if n == "TailRotor" else Vector3.UP)
			spin_parts.append([p, axis, p.transform])
	for n in ["AileronL", "AileronR", "Elevator", "Rudder"]:
		var f := model_root.find_child(n, true, false) as Node3D
		if f:
			flaps[f] = f.transform
	for n in model_root.find_children("Deer*", "", true, false):
		var node := n as Node3D
		deer.append({"node": node, "rest": node.transform, "leg": node.name.contains("Leg"), "front": node.name.contains("LegF")})
	# Collision: a box around the body.
	var box := AABB()
	var first := true
	for mi in model_root.find_children("*", "MeshInstance3D", true, false):
		var b := (mi as Node3D).transform * (mi as MeshInstance3D).get_aabb()
		if (mi as Node).name in ["Rotor", "Propeller"] or (mi as Node).name.begins_with("Deer"):
			continue  # blades and reindeer don't bump into things
		box = b if first else box.merge(b)
		first = false
	if first:
		box = AABB(Vector3(-0.5, 0, -1), Vector3(1, 0.8, 2))
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(box.size.x * 0.9, maxf(box.size.y * 0.8, 0.3), box.size.z * 0.9)
	cs.shape = shape
	cs.position = box.get_center() + Vector3(0, box.size.y * 0.1, 0)
	add_child(cs)
	set_meta("half_size", shape.size / 2)
	if style == "rocket":
		exhaust = make_exhaust()
	fx = Node3D.new()
	fx.set_script(preload("res://ride_fx.gd"))
	fx.main = main
	add_child(fx)
	fx.setup(self, k)
	engine_snd = AudioStreamPlayer3D.new()
	engine_snd.stream = Rides.synth("rotor" if k == "helicopter" else ("jet" if style == "rocket" or spec.get("low", false) else "engine"))
	engine_snd.volume_db = -12.0
	engine_snd.unit_size = 8.0
	add_child(engine_snd)
	global_transform = at
	yaw = atan2(at.basis.z.x, at.basis.z.z)


func stand_in() -> Node3D:
	var root := Node3D.new()
	var b := MeshInstance3D.new()
	b.name = "Body"
	var m := StandardMaterial3D.new()
	m.albedo_color = Color("d84a3a") if kind != "helicopter" else Color("e8c02a")
	if style == "rocket":
		var c := CylinderMesh.new()
		c.top_radius = 0.1
		c.bottom_radius = 0.4
		c.height = 2.2
		c.material = m
		b.mesh = c
		b.position.y = 1.1
	else:
		var bm := BoxMesh.new()
		bm.size = Vector3(0.8, 0.5, 1.8) if not spec.get("low", false) else Vector3(0.5, 0.08, 1.0)
		bm.material = m
		b.mesh = bm
		b.position.y = bm.size.y / 2 + 0.05
	root.add_child(b)
	if style == "plane":
		var w := MeshInstance3D.new()
		var wm := BoxMesh.new()
		wm.size = Vector3(3.0, 0.06, 0.6)
		wm.material = m
		w.mesh = wm
		w.position = Vector3(0, 0.45, 0.2)
		root.add_child(w)
	var seat_node := Node3D.new()
	seat_node.name = "Seat"
	seat_node.position = Vector3(0, 0.5 if style != "rocket" else 1.2, 0)
	root.add_child(seat_node)
	return root


func set_driver(character: String) -> void:
	if driver:
		driver.queue_free()
		driver = null
	if character != "":
		driver = Rides.seat_driver(model_root, seat, character, spec.get("low", false))


func velocity_now() -> Vector3:
	return velocity


func boost() -> void:
	boost_t = 1.2


func hop() -> void:
	velocity.y += 6.0


func stunt() -> void:
	if style == "plane" and not is_on_floor():
		loop_t = 1.6


func _physics_process(delta: float) -> void:
	t += delta
	var live: bool = driving and not main.busy and not main.menu_open()
	var fwd_in := 0.0
	var turn_in := 0.0
	var up_in := 0.0
	if live:
		fwd_in = float(Input.is_key_pressed(KEY_W)) - float(Input.is_key_pressed(KEY_S))
		turn_in = float(Input.is_key_pressed(KEY_A)) - float(Input.is_key_pressed(KEY_D))
		up_in = float(Input.is_key_pressed(KEY_SPACE)) - float(Input.is_key_pressed(KEY_SHIFT))
	boost_t -= delta
	var top: float = spec.top * (1.8 if boost_t > 0.0 else 1.0)
	var grounded := is_on_floor()
	var height := ground_height()

	match style:
		"hover":
			yaw += turn_in * 1.8 * delta
			var fwd := Vector3(sin(yaw), 0, cos(yaw))
			var want := fwd * fwd_in * top
			velocity.x = move_toward(velocity.x, want.x, 14.0 * delta)
			velocity.z = move_toward(velocity.z, want.z, 14.0 * delta)
			var ceiling := 3.0 if spec.get("low", false) else 60.0  # boards and jetpacks stay low
			if not driving:
				velocity.y = move_toward(velocity.y, -6.0, 10.0 * delta)
			elif up_in != 0.0:
				velocity.y = move_toward(velocity.y, up_in * 6.0, 16.0 * delta)
			else:
				velocity.y = move_toward(velocity.y, 0.0, 8.0 * delta)  # hangs in the air
			if height > ceiling and velocity.y > 0.0:
				velocity.y = 0.0
			if spec.get("low", false) and driving and height < 0.35:
				velocity.y = maxf(velocity.y, 2.0)  # hover off the ground
			pitch = lerpf(pitch, fwd_in * 0.18, 4.0 * delta)  # nose dips going forward
			bank = lerpf(bank, turn_in * 0.3 * clampf(Vector2(velocity.x, velocity.z).length() / top, 0.2, 1.0), 4.0 * delta)
		"plane":
			speed = move_toward(speed, clampf(speed + fwd_in * 10.0, 0.0, top), 6.0 * delta) if driving else move_toward(speed, 0.0, 6.0 * delta)
			var flying := speed > 7.0
			yaw += turn_in * (1.3 if flying else 1.6) * delta * clampf(speed / 6.0, 0.2, 1.0)
			bank = lerpf(bank, turn_in * (0.6 if flying else 0.0), 3.0 * delta)  # lean into the turn
			var climb := up_in * 0.45 if flying else 0.0
			if grounded and climb < 0.0:
				climb = 0.0
			if loop_t > 0.0:
				loop_t -= delta
				pitch -= TAU / 1.6 * delta
				climb = 0.0
			else:
				pitch = lerpf(wrapf(pitch, -PI, PI), -climb, 3.0 * delta)
			var fwd := Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch) * Vector3.BACK
			velocity = fwd * speed
			if not flying:
				velocity.y = -4.0 if not grounded else 0.0  # too slow to fly
		"rocket":
			yaw += turn_in * 1.6 * delta
			lift = move_toward(lift, maxf(up_in, 0.0) + (0.6 if boost_t > 0.0 else 0.0), 3.0 * delta)
			pitch = lerpf(pitch, fwd_in * 0.6 if not grounded else 0.0, 2.5 * delta)
			# The rocket stands on its tail; thrust pushes along its nose.
			var nose := Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch) * Vector3.UP
			velocity += nose * lift * 26.0 * delta
			velocity.y -= 9.0 * delta
			velocity = velocity.limit_length(top)
			if grounded and lift < 0.1:
				velocity = velocity.move_toward(Vector3.ZERO, 20.0 * delta)
	if not driving and style != "hover":
		velocity.y -= 9.0 * delta
	move_and_slide()
	# Face the way we're going.
	var b := Basis(Vector3.UP, yaw)
	if style == "rocket":
		b = b * Basis(Vector3.RIGHT, pitch)
	else:
		b = b * Basis(Vector3.FORWARD, bank) * Basis(Vector3.RIGHT, pitch)
	global_basis = b.orthonormalized()
	if global_position.y < -20.0:
		global_transform = spawn_xf
		velocity = Vector3.ZERO

	# Spinning blades, galloping reindeer, a bobbing hoverboard.
	var power := 1.0 if driving else 0.15
	for sp in spin_parts:
		(sp[0] as Node3D).transform = (sp[2] as Transform3D) * Transform3D(Basis(sp[1], t * 40.0 * power), Vector3.ZERO)
	for d in deer:
		var rest: Transform3D = d.rest
		var gallop := sin(t * 11.0 + (0.0 if d.front else PI)) * 0.6 * (1.0 if driving else 0.1)
		if d.leg:
			(d.node as Node3D).transform = rest * Transform3D(Basis(Vector3.RIGHT, gallop), Vector3.ZERO)
		elif (d.node as Node).name.contains("Body"):
			(d.node as Node3D).transform = Transform3D(rest.basis, rest.origin + Vector3(0, absf(sin(t * 11.0)) * 0.04 * power, 0))
	if spec.get("low", false):
		model_root.position.y = sin(t * 3.0) * 0.03
	if exhaust:
		exhaust.emitting = lift > 0.1
		exhaust.initial_velocity_max = 3.0 + lift * 5.0
	# Plane flaps follow the stick.
	turn_now = lerpf(turn_now, turn_in, 6.0 * delta)
	for f in flaps:
		var rest: Transform3D = flaps[f]
		var name: String = (f as Node).name
		var a := 0.0
		var axis := Vector3.RIGHT
		match name:
			"AileronL":
				a = turn_now * 0.4
			"AileronR":
				a = -turn_now * 0.4
			"Elevator":
				a = -up_in * 0.4
			"Rudder":
				a = turn_now * 0.4
				axis = Vector3.UP
		(f as Node3D).transform = rest * Transform3D(Basis(axis, a), Vector3.ZERO)

	if engine_snd:
		if driving and not engine_snd.playing:
			engine_snd.play()
		elif not driving and engine_snd.playing:
			engine_snd.stop()
		engine_snd.pitch_scale = 0.8 + clampf(velocity.length() / spec.top, 0.0, 1.0) * 0.7

	# Smash builds when crashing into them.
	for i in get_slide_collision_count():
		var c := get_slide_collision(i).get_collider()
		if c and (c as Node).has_meta("tile") and velocity.length() > 3.0 and not main.busy:
			main.destroyer.shatter(global_position, velocity * 0.5, clampf(velocity.length() * 0.6, 2.5, 7.0), 4.0)
			break


func ground_height() -> float:
	var q := PhysicsRayQueryParameters3D.create(global_position, global_position + Vector3.DOWN * 80.0, 1 | 2)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	return global_position.y - (hit.position as Vector3).y if not hit.is_empty() else 80.0


func right_side_up() -> void:
	pitch = 0.0
	bank = 0.0
	velocity = Vector3.ZERO


func make_exhaust() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.amount = 200
	p.lifetime = 0.45
	p.emitting = false
	p.local_coords = false
	p.direction = Vector3.DOWN
	p.spread = 10.0
	p.initial_velocity_min = 3.0
	p.initial_velocity_max = 6.0
	p.gravity = Vector3.ZERO
	p.scale_amount_min = 0.8
	p.scale_amount_max = 1.8
	var q := QuadMesh.new()
	q.size = Vector2(0.22, 0.22)
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
	g.set_color(0, Color(1.0, 0.95, 0.6, 1.0))
	g.add_point(0.35, Color(1.0, 0.5, 0.1, 0.9))
	g.set_color(g.get_point_count() - 1, Color(0.4, 0.4, 0.4, 0.0))
	p.color_ramp = g
	var at := model_root.find_child("Flame", true, false) as Node3D
	if at:
		at.add_child(p)
	else:
		model_root.add_child(p)
	return p
