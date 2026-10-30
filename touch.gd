extends Control
## On-screen controls for the iPad.
##
## They work by pressing the same keys the keyboard would, so the rest of the
## game doesn't need to know about touch at all:
##  - a thumb stick (bottom left) presses W A S D
##  - big buttons (bottom right) press Space, Shift, F, G, Enter...
##  - two fingers anywhere: drag to turn the camera, pinch to zoom
##  - building: one finger drags the camera around the lot
## Taps on the world still place tiles (Godot turns a tap into a mouse click).

var main: Node
var stick_base: Control
var stick_knob: Control
var stick_finger := -1
var stick_centre := Vector2.ZERO
var held := {}  # keycode -> true while pressed by touch
var buttons: Array = []  # {node, key, modes}
var fingers := {}  # index -> position (for two-finger camera)
var pinch_dist := 0.0

const STICK_R := 90.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	stick_base = circle(STICK_R * 2, Color(1, 1, 1, 0.18), Color(1, 1, 1, 0.5))
	stick_base.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	add_child(stick_base)
	stick_knob = circle(80, Color(1, 1, 1, 0.55), Color(1, 1, 1, 0.9))
	stick_base.add_child(stick_knob)
	# Right-hand buttons: [label, key, which modes show it]
	var defs := [
		["Jump", KEY_SPACE, ["walk"]], ["Fight!", KEY_F, ["walk"]], ["Stone", KEY_T, ["walk"]], ["Hop in", KEY_ENTER, ["walk_near"]],
		["Up", KEY_SPACE, ["fly"]], ["Down", KEY_SHIFT, ["fly"]], ["Brake", KEY_SPACE, ["car"]],
		["Special", KEY_F, ["car", "fly"]], ["Honk", KEY_G, ["car", "fly"]], ["Hop out", KEY_ENTER, ["car", "fly"]],
		["Tilt +", KEY_F, ["build"]], ["Tilt -", KEY_G, ["build"]], ["Turn", KEY_R, ["build"]],
	]
	for d in defs:
		var b := Button.new()
		b.text = d[0]
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(120, 96)
		b.add_theme_font_size_override("font_size", 24)
		b.mouse_filter = Control.MOUSE_FILTER_STOP
		var key: int = d[1]
		b.button_down.connect(func(): press(key, true))
		b.button_up.connect(func(): press(key, false))
		add_child(b)
		buttons.append({"node": b, "key": key, "modes": d[2]})
	resized.connect(layout)
	layout()


func circle(size: float, fill: Color, edge: Color) -> Panel:
	var p := Panel.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = fill
	sb.border_color = edge
	sb.set_border_width_all(4)
	sb.set_corner_radius_all(int(size / 2))
	p.add_theme_stylebox_override("panel", sb)
	p.size = Vector2(size, size)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return p


func layout() -> void:
	var vs := size
	stick_base.position = Vector2(60, vs.y - STICK_R * 2 - 230)
	stick_knob.position = Vector2(STICK_R - 40, STICK_R - 40)


func mode() -> String:
	if not main.play_mode:
		return "build"
	if main.driving:
		return "car" if main.Rides.RIDES[main.ride.kind].type == "car" else "fly"
	return "walk"


func _process(_delta: float) -> void:
	var m := mode()
	stick_base.visible = true  # walks, drives, or slides the camera while building
	var shown: Array = []
	for b in buttons:
		var on: bool = m in b.modes or (m == "walk" and "walk_near" in b.modes and main.near_buggy())
		(b.node as Button).visible = on and not main.menu_open() and not main.busy
		if (b.node as Button).visible:
			shown.append(b.node)
	# Stack the visible buttons in a 2-wide column above the toolbar, bottom right.
	var vs := size
	for i in shown.size():
		var b: Button = shown[i]
		var col := i % 2
		var row := i / 2
		b.position = Vector2(vs.x - 140 - col * 136, vs.y - 330 - row * 110)


func press(key: int, down: bool) -> void:
	if held.get(key, false) == down:
		return
	held[key] = down
	var ev := InputEventKey.new()
	ev.keycode = key
	ev.physical_keycode = key
	ev.pressed = down
	Input.parse_input_event(ev)


func _input(ev: InputEvent) -> void:
	if ev is InputEventScreenTouch:
		var t := ev as InputEventScreenTouch
		if t.pressed:
			var r := Rect2(stick_base.global_position - Vector2(40, 40), stick_base.size + Vector2(80, 80))
			if stick_base.visible and stick_finger == -1 and r.has_point(t.position):
				stick_finger = t.index
				main.tap_ok = false  # pushing the stick never places a tile
				stick_centre = stick_base.global_position + stick_base.size / 2
				move_stick(t.position)
				get_viewport().set_input_as_handled()
				return
			fingers[t.index] = t.position
			pinch_dist = 0.0
			if fingers.size() > 1:
				main.tap_ok = false  # a two-finger turn isn't a tap
		else:
			if t.index == stick_finger:
				stick_finger = -1
				move_stick(stick_centre)
				get_viewport().set_input_as_handled()
			fingers.erase(t.index)
	elif ev is InputEventScreenDrag:
		var d := ev as InputEventScreenDrag
		if d.index == stick_finger:
			move_stick(d.position)
			get_viewport().set_input_as_handled()
			return
		fingers[d.index] = d.position
		if fingers.size() == 2:
			# Two fingers: drag turns the camera, pinch zooms.
			var pts: Array = fingers.values()
			var dist: float = (pts[0] as Vector2).distance_to(pts[1])
			if pinch_dist > 0.0:
				main.cam_dist = clampf(main.cam_dist * pinch_dist / dist, 1.5, 60.0)
			pinch_dist = dist
			main.cam_yaw -= d.relative.x * 0.004
			main.cam_pitch = clampf(main.cam_pitch + d.relative.y * 0.003, 0.05, 1.45)
			get_viewport().set_input_as_handled()
		elif fingers.size() == 1 and not main.play_mode:
			# One finger while building: drag the lot around (a tap still places).
			main.pan_camera(d.relative)
			if d.position.distance_to(main.tap_pos) > 14.0:
				main.tap_ok = false
		elif fingers.size() == 1 and main.play_mode:
			# One finger on the world while exploring: look around.
			main.cam_yaw -= d.relative.x * 0.006
			main.cam_pitch = clampf(main.cam_pitch + d.relative.y * 0.004, 0.05, 1.45)


func move_stick(p: Vector2) -> void:
	var off := (p - stick_centre).limit_length(STICK_R)
	stick_knob.position = Vector2(STICK_R - 40, STICK_R - 40) + off
	var v := off / STICK_R
	press(KEY_W, v.y < -0.35)
	press(KEY_S, v.y > 0.35)
	press(KEY_A, v.x < -0.35)
	press(KEY_D, v.x > 0.35)
