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
var swing_t := 0.0  # > 0 while an attack plays
var swing_len := 0.35
var swing_kind := "fists"
var hurt_t := 0.0


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
	# Re-attach whatever weapon was in hand.
	if main and main.combat:
		main.combat.equip.call_deferred(main.combat.current)
	# Pop in.
	visual.scale = Vector3(0.6, 1.3, 0.6)
	create_tween().tween_property(visual, "scale", Vector3.ONE, 0.35).set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= GRAVITY * delta

	var x := 0.0
	var z := 0.0
	if Input.is_key_pressed(KEY_W):
		z -= 1.0
	if Input.is_key_pressed(KEY_S):
		z += 1.0
	if Input.is_key_pressed(KEY_A):
		x -= 1.0
	if Input.is_key_pressed(KEY_D) or auto_walk:
		x += 1.0

	# Move relative to where the camera is looking.
	var yaw: float = main.cam_yaw
	var fwd := Vector3(-sin(yaw), 0, -cos(yaw))
	var right := Vector3(cos(yaw), 0, -sin(yaw))
	var dir := fwd * -z + right * x
	if dir.length() > 1.0:
		dir = dir.normalized()
	if hurt_t <= 0.0:
		velocity.x = dir.x * SPEED
		velocity.z = dir.z * SPEED

	if main.menu_open() or main.busy:
		dir = Vector3.ZERO
		velocity.x = 0.0
		velocity.z = 0.0
	if hurt_t > 0.0:
		hurt_t -= delta
		velocity.x = move_toward(velocity.x, 0.0, 8.0 * delta)  # still sliding from the hit
		velocity.z = move_toward(velocity.z, 0.0, 8.0 * delta)
	if is_on_floor() and Input.is_key_pressed(KEY_SPACE) and not main.menu_open():
		velocity.y = JUMP

	move_and_slide()

	if dir.length() > 0.1:
		var visual := $Visual as Node3D
		visual.rotation.y = lerp_angle(visual.rotation.y, atan2(-dir.x, -dir.z), 12.0 * delta)

	if global_position.y < -10.0:
		global_position = spawn
		velocity = Vector3.ZERO

	animate(delta)


func hand() -> Node3D:
	# A node at the end of the right arm, for holding weapons.
	if not parts.has("ArmR"):
		return null
	var arm: Node3D = parts.ArmR.node
	var h := arm.get_node_or_null("Hand") as Node3D
	if h == null:
		h = Node3D.new()
		h.name = "Hand"
		var lo := 0.0
		var mi := arm as MeshInstance3D if arm is MeshInstance3D else arm.find_child("*", true, false) as MeshInstance3D
		if mi:
			var box := mi.get_aabb()
			lo = box.position.y + box.size.y * 0.12
			h.position = Vector3(box.get_center().x, lo, box.get_center().z)
		arm.add_child(h)
	return h


func facing() -> Vector3:
	var v := $Visual as Node3D
	return Vector3(-sin(v.rotation.y), 0, -cos(v.rotation.y))


func face(dir: Vector3) -> void:
	($Visual as Node3D).rotation.y = atan2(-dir.x, -dir.z)


func swing(length: float, kind: String) -> void:
	swing_t = length
	swing_len = length
	swing_kind = kind


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
	# Attacks: melee swings chop down from overhead; ranged weapons point forward.
	swing_t -= delta
	var k := clampf(1.0 - swing_t / swing_len, 0.0, 1.0) if swing_t > 0.0 else 1.0
	var arm_r := Vector3(swing * 0.9 - breathe * 0.04, 0, 0.15 * moving + 2.3 * air)
	var holding: bool = main and main.combat and main.combat.current != "fists"
	if holding:
		arm_r.x = -0.9 + swing * 0.2  # carry the weapon out in front
	if swing_t > 0.0:
		if main.combat.WEAPONS[swing_kind].melee:
			arm_r = Vector3(lerpf(-2.8, -0.3, ease(k, 0.4)), 0, 0.2)
		else:
			arm_r = Vector3(-1.55, 0, 0.05 + (1.0 - k) * 0.15)
	pose("ArmR", arm_r)
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
