extends CharacterBody3D
## Little explorer you drive around your builds in Play mode.
##
## Characters are toy figures made of rigid parts (Body, Head, ArmL/R, LegL/R,
## Tail) whose origins sit at the joints, so walking is just swinging those parts.

const SPEED := 2.6
const JUMP := 5.6
const GRAVITY := 14.0
const MODEL_SCALE := 0.55
const PARTS := ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Tail"]

var main: Node3D
var spawn := Vector3(0, 2, 0)
var character := ""
var auto_walk := false  # testing: walk sideways on its own

var model: Node3D
var parts := {}  # name -> rest Transform3D, keyed by node
var phase := 0.0
var idle_t := 0.0
var air := 0.0
var was_on_floor := true


func set_character(name: String) -> void:
	character = name
	if model:
		model.queue_free()
	model = (load("res://assets/characters/%s.glb" % name) as PackedScene).instantiate()
	model.scale = Vector3.ONE * MODEL_SCALE
	model.rotation.y = PI  # models face +Z after import; Visual faces -Z
	var visual := $Visual as Node3D
	visual.add_child(model)
	parts.clear()
	for n in PARTS:
		var node := model.find_child(n, true, false) as Node3D
		if node:
			parts[n] = {"node": node, "rest": node.transform}
	# Pop in.
	visual.scale = Vector3(0.6, 1.3, 0.6)
	create_tween().tween_property(visual, "scale", Vector3.ONE, 0.35).set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= GRAVITY * delta

	var x := 0.0
	var z := 0.0
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		z -= 1.0
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		z += 1.0
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		x -= 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT) or auto_walk:
		x += 1.0

	# Move relative to where the camera is looking.
	var yaw: float = main.cam_yaw
	var fwd := Vector3(-sin(yaw), 0, -cos(yaw))
	var right := Vector3(cos(yaw), 0, -sin(yaw))
	var dir := fwd * -z + right * x
	if dir.length() > 1.0:
		dir = dir.normalized()
	velocity.x = dir.x * SPEED
	velocity.z = dir.z * SPEED

	if is_on_floor() and Input.is_key_pressed(KEY_SPACE):
		velocity.y = JUMP

	move_and_slide()

	if dir.length() > 0.1:
		var visual := $Visual as Node3D
		visual.rotation.y = lerp_angle(visual.rotation.y, atan2(-dir.x, -dir.z), 12.0 * delta)

	if global_position.y < -10.0:
		global_position = spawn
		velocity = Vector3.ZERO

	animate(delta)


func pose(part: String, rot: Vector3) -> void:
	if not parts.has(part):
		return
	var p: Dictionary = parts[part]
	var rest: Transform3D = p.rest
	(p.node as Node3D).transform = Transform3D(rest.basis * Basis.from_euler(rot), rest.origin)


func animate(delta: float) -> void:
	if model == null:
		return
	var on_floor := is_on_floor()
	var hspeed := Vector2(velocity.x, velocity.z).length()
	var moving := clampf(hspeed / SPEED, 0.0, 1.0)
	phase += hspeed * delta * 5.5
	idle_t += delta
	air = move_toward(air, 0.0 if on_floor else 1.0, delta * 7.0)
	var ground := 1.0 - air

	var swing := sin(phase) * 0.75 * moving * ground
	var breathe := sin(idle_t * 2.2)
	pose("LegL", Vector3(swing - 0.55 * air, 0, 0))
	pose("LegR", Vector3(-swing + 0.35 * air, 0, 0))
	# Arms swing opposite to legs; fling up and out when jumping.
	pose("ArmL", Vector3(-swing * 0.9 + breathe * 0.04, 0, -0.15 * moving - 2.3 * air))
	pose("ArmR", Vector3(swing * 0.9 - breathe * 0.04, 0, 0.15 * moving + 2.3 * air))
	pose("Head", Vector3(0.06 * sin(phase * 2.0) * moving - 0.15 * air, 0.12 * sin(idle_t * 0.7) * (1.0 - moving), 0.06 * sin(idle_t * 1.3)))
	pose("Tail", Vector3(0, sin(idle_t * (5.0 + 6.0 * moving)) * (0.25 + 0.2 * moving), 0))
	pose("Body", Vector3(0, 0, 0.04 * sin(phase) * moving))

	# Bouncy steps and a little squash when landing.
	model.position.y = absf(sin(phase)) * 0.035 * moving * ground + breathe * 0.004
	if on_floor and not was_on_floor:
		var visual := $Visual as Node3D
		visual.scale = Vector3(1.15, 0.8, 1.15)
		create_tween().tween_property(visual, "scale", Vector3.ONE, 0.25).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	was_on_floor = on_floor
