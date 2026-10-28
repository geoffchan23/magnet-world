extends VehicleBody3D
## A ground vehicle: the buggy, fire truck, police car, garbage truck, race car,
## monster truck or ice cream truck (see rides.gd). Walk up to one in Explore
## mode and press Enter to hop in.
##
## W / S  gas and brake (hold S to reverse), A / D steer, Space handbrake,
## F special move, G horn, R flips it back onto its wheels, Enter hops out.
## Crash into your build fast enough and it smashes to pieces (Z puts it back).
##
## Models (assets/vehicles/<kind>.glb) have a Body, wheels with their origins at
## the hubs (WheelFL/FR/RL/RR, maybe WheelML/MR), and a Seat empty where the
## driver sits; the driver is a copy of your explorer, posed sitting down.

const Rides := preload("res://rides.gd")
const BRAKE := 6.0
const MAX_STEER := 0.55
const LAYER := 32

var ENGINE := 210.0  # per wheel (all of them drive)
var REVERSE := 120.0
var MAX_SPEED := 13.0
var main: Node3D
var kind := "buggy"
var fx: Node3D  # ride_fx.gd: special move + horn
var driving := false
var steer_now := 0.0
var upside_down_for := 0.0
var driver: Node3D  # the explorer sitting in the seat
var seat := Transform3D(Basis(), Vector3(0, 0.35, -0.15))
var wheels: Array = []
var steering_wheel: Node3D
var steering_rest := Transform3D()
var engine_snd: AudioStreamPlayer3D
var spawn_xf := Transform3D()


func setup(at: Transform3D, k := "buggy") -> void:
	kind = k
	var spec: Dictionary = Rides.RIDES[k]
	ENGINE = spec.engine
	REVERSE = ENGINE * 0.55
	MAX_SPEED = spec.top
	spawn_xf = at
	collision_layer = LAYER
	collision_mask = 1 | 2 | 8 | LAYER | 64
	mass = spec.mass
	center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	center_of_mass = Vector3(0, 0.22, 0)
	can_sleep = false
	contact_monitor = true
	max_contacts_reported = 4
	body_entered.connect(_on_hit)
	var path := Rides.model_path(k)
	var model: Node3D = (load(path) as PackedScene).instantiate() if ResourceLoader.exists(path) else stand_in()
	var hubs := {}
	for n in ["WheelFL", "WheelFR", "WheelML", "WheelMR", "WheelRL", "WheelRR"]:
		var w := model.find_child(n, true, false) as Node3D
		if w:
			hubs[n] = w
	var seat_node := model.find_child("Seat", true, false) as Node3D
	if seat_node:
		seat = Transform3D(Basis(), seat_node.position + Vector3(0, -0.094, 0))  # Seat is the cushion top; figures stand on their origin
	steering_wheel = model.find_child("Steering", true, false) as Node3D
	# Re-home everything except the wheels under the vehicle body.
	for n in model.get_children():
		if not hubs.has((n as Node).name) and n is Node3D:
			var xf: Transform3D = (n as Node3D).transform
			model.remove_child(n)
			add_child(n)
			(n as Node3D).transform = xf
	if steering_wheel:
		steering_rest = steering_wheel.transform
	var lo := Vector3(INF, INF, INF)
	var hi := Vector3(-INF, -INF, -INF)
	for n in hubs:
		var w: Node3D = hubs[n]
		var vw := VehicleWheel3D.new()
		vw.name = n
		var front: bool = n.begins_with("WheelF")
		# Wheel size comes from the tyre mesh itself.
		var radius := 0.3
		if w is MeshInstance3D:
			radius = (w as MeshInstance3D).get_aabb().size.y / 2.0
		var travel: float = spec.get("travel", 0.14)
		vw.position = w.position + Vector3(0, travel * 0.55, 0)  # the springs settle a little under load
		vw.use_as_steering = front
		vw.use_as_traction = true
		vw.wheel_radius = radius
		vw.wheel_rest_length = travel * 0.85
		vw.suspension_travel = travel
		vw.suspension_stiffness = 45.0 if travel < 0.2 else 28.0
		vw.suspension_max_force = 6000.0
		vw.damping_compression = 1.6
		vw.damping_relaxation = 2.2
		vw.wheel_friction_slip = spec.get("grip", 3.2)
		vw.wheel_roll_influence = 0.15
		add_child(vw)
		# The tyre mesh spins and steers with the wheel.
		w.get_parent().remove_child(w)
		vw.add_child(w)
		w.transform = Transform3D(w.transform.basis, Vector3.ZERO)
		wheels.append(vw)
		lo = lo.min(w.position + vw.position)
		hi = hi.max(vw.position)
	model.queue_free()
	# The chassis box: the body's footprint, sitting above the wheels so the
	# suspension does the work.
	var body_box := AABB()
	var body_mesh := get_node_or_null("Body") as MeshInstance3D
	if body_mesh:
		body_box = body_mesh.transform * body_mesh.get_aabb()
	else:
		body_box = AABB(Vector3(-0.5, 0.3, -1.0), Vector3(1.0, 0.6, 2.0))
	var floor_y: float = hi.y + 0.05
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(body_box.size.x * 0.92, maxf(body_box.end.y - floor_y, 0.3), body_box.size.z * 0.95)
	cs.shape = box
	cs.position = Vector3(body_box.get_center().x, floor_y + box.size.y / 2, body_box.get_center().z)
	add_child(cs)
	set_meta("half_size", Vector3(box.size.x / 2, (floor_y + box.size.y) / 2, box.size.z / 2))
	center_of_mass = Vector3(0, hi.y * 0.8, 0)
	var phys := PhysicsMaterial.new()
	phys.friction = 0.6
	phys.bounce = 0.1
	physics_material_override = phys
	fx = Node3D.new()
	fx.set_script(preload("res://ride_fx.gd"))
	fx.main = main
	add_child(fx)
	fx.setup(self, k)
	engine_snd = AudioStreamPlayer3D.new()
	engine_snd.stream = Rides.synth("engine")
	engine_snd.volume_db = -14.0
	engine_snd.unit_size = 6.0
	add_child(engine_snd)
	global_transform = at


func stand_in() -> Node3D:
	# Plain shapes, until the Blender buggy exists.
	var root := Node3D.new()
	var b := MeshInstance3D.new()
	b.name = "Body"
	var bm := BoxMesh.new()
	bm.size = Vector3(1.0, 0.4, 2.0)
	var m := StandardMaterial3D.new()
	m.albedo_color = Color("e8742a")
	bm.material = m
	b.mesh = bm
	b.position.y = 0.55
	root.add_child(b)
	for n in ["WheelFL", "WheelFR", "WheelRL", "WheelRR"]:
		var w := MeshInstance3D.new()
		w.name = n
		var cm := CylinderMesh.new()
		cm.top_radius = 0.3
		cm.bottom_radius = 0.3
		cm.height = 0.22
		var tm := StandardMaterial3D.new()
		tm.albedo_color = Color("222222")
		cm.material = tm
		w.mesh = cm
		w.rotation.z = PI / 2
		var x := 0.6 if n.ends_with("L") else -0.6
		var z := 0.75 if n[5] == "F" else -0.75
		w.position = Vector3(x, 0.3, z)
		root.add_child(w)
	return root


func set_driver(character: String) -> void:
	if driver:
		driver.queue_free()
		driver = null
	if character != "":
		driver = Rides.seat_driver(self, seat, character)


func velocity_now() -> Vector3:
	return linear_velocity


func boost() -> void:
	apply_central_impulse(global_basis.z * mass * 6.0)


func hop() -> void:
	apply_central_impulse(Vector3.UP * mass * 6.5)
	main.shake = 0.3


func stunt() -> void:
	pass


func _physics_process(delta: float) -> void:
	var gas := 0.0
	var steer_in := 0.0
	var hand := false
	if driving and not main.busy and not main.menu_open():
		if Input.is_key_pressed(KEY_W):
			gas += 1.0
		if Input.is_key_pressed(KEY_S):
			gas -= 1.0
		if Input.is_key_pressed(KEY_A):
			steer_in += 1.0
		if Input.is_key_pressed(KEY_D):
			steer_in -= 1.0
		hand = Input.is_key_pressed(KEY_SPACE)
	var fwd_speed := linear_velocity.dot(global_basis.z)
	# Less steering at speed, so it doesn't spin out.
	var steer_max := MAX_STEER * lerpf(1.0, 0.45, clampf(absf(fwd_speed) / MAX_SPEED, 0.0, 1.0))
	steer_now = move_toward(steer_now, steer_in * steer_max, delta * 2.6)
	steering = steer_now
	if gas > 0.0:
		engine_force = ENGINE * gas if fwd_speed < MAX_SPEED else 0.0
		brake = BRAKE if fwd_speed < -0.5 else 0.0
	elif gas < 0.0:
		if fwd_speed > 0.8:
			engine_force = 0.0
			brake = BRAKE
		else:
			engine_force = -REVERSE if fwd_speed > -MAX_SPEED * 0.4 else 0.0
			brake = 0.0
	else:
		engine_force = 0.0
		brake = 0.6  # rolls to a stop
	if hand:
		engine_force = 0.0
		for w in wheels:
			(w as VehicleWheel3D).brake = BRAKE * 2.0 if (w as Node).name.begins_with("WheelR") else 0.0
	else:
		for w in wheels:
			(w as VehicleWheel3D).brake = brake
	if steering_wheel:
		steering_wheel.transform = steering_rest * Transform3D(Basis(Vector3.UP, steer_now * 2.5), Vector3.ZERO)  # its local Y is the column

	# Stuck on its roof or side? Pop back up after a moment (or right away with R).
	if global_basis.y.y < 0.35 and linear_velocity.length() < 1.5:
		upside_down_for += delta
	else:
		upside_down_for = 0.0
	if upside_down_for > 2.0 or global_position.y < -20.0:
		right_side_up()

	if engine_snd:
		if driving and not engine_snd.playing:
			engine_snd.play()
		elif not driving and engine_snd.playing:
			engine_snd.stop()
		engine_snd.pitch_scale = 0.7 + clampf(absf(fwd_speed) / MAX_SPEED, 0.0, 1.0) * 0.9 + absf(gas) * 0.15


func _on_hit(other: Node) -> void:
	var speed := linear_velocity.length()
	if other.has_meta("tile") and speed > 3.0 and not main.busy:
		main.destroyer.shatter(global_position + global_basis.z * 0.9, linear_velocity * 0.5, clampf(speed * 0.6, 2.5, 7.0), 4.0)


func right_side_up() -> void:
	upside_down_for = 0.0
	var yaw := atan2(global_basis.z.x, global_basis.z.z)
	var p := global_position
	if p.y < -20.0:
		global_transform = spawn_xf
	else:
		global_transform = Transform3D(Basis(Vector3.UP, yaw), Vector3(p.x, maxf(p.y, 0.0) + 0.8, p.z))
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
