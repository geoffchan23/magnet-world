extends CharacterBody3D
## Little explorer you drive around your builds in Play mode.

const SPEED := 2.6
const JUMP := 5.6
const GRAVITY := 14.0

var main: Node3D
var spawn := Vector3(0, 2, 0)


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
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
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
