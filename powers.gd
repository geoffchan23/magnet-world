extends Node3D
## The Infinity Gauntlet (weapon slot 9). Each stone you find gives it a power;
## T picks which stone to use and F uses it:
##   Space   - teleport to where you're looking
##   Mind    - nearby baddies fight on your side for a while
##   Reality - nearby baddies turn into bubbles and sweets
##   Power   - a huge purple shockwave
##   Time    - freeze every baddie around you
##   Soul    - all hearts back, and a golden shield
## With all six you can do the Snap: every baddie in the city turns to dust.

const Stones := preload("res://stones.gd")
const POWER_TEXT := {
	"space": "Gauntlet power: teleport where you look!",
	"mind": "Gauntlet power: baddies fight for you!",
	"reality": "Gauntlet power: turn baddies into bubbles!",
	"power": "Gauntlet power: a giant shockwave!",
	"time": "Gauntlet power: freeze time!",
	"soul": "Gauntlet power: heal up and get a shield!",
	"snap": "THE SNAP: all the baddies turn to dust!",
}
const COOLDOWN := {"space": 1.0, "mind": 6.0, "reality": 5.0, "power": 3.0, "time": 10.0, "soul": 15.0, "snap": 25.0}

var main: Node3D
var selected := ""  # which stone F uses ("snap" once you have all six)
var ready_at := {}  # power -> time it can be used again
var hud: HBoxContainer
var hud_icons := {}  # stone -> TextureRect/Panel
var hud_label: Label


func _ready() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.position.y = 12
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(box)
	hud = HBoxContainer.new()
	hud.alignment = BoxContainer.ALIGNMENT_CENTER
	hud.add_theme_constant_override("separation", 6)
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(hud)
	for stone in Stones.ORDER:
		var p := Panel.new()
		p.custom_minimum_size = Vector2(46, 46)
		p.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var icon_path := "res://assets/weapons/stone_%s.png" % stone
		if ResourceLoader.exists(icon_path):
			var tr := TextureRect.new()
			tr.texture = load(icon_path)
			tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			tr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			tr.offset_left = 4
			tr.offset_top = 4
			tr.offset_right = -4
			tr.offset_bottom = -4
			tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
			p.add_child(tr)
		else:
			var dot := Panel.new()
			var sb := StyleBoxFlat.new()
			sb.bg_color = Stones.STONES[stone].color
			sb.set_corner_radius_all(14)
			dot.add_theme_stylebox_override("panel", sb)
			dot.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			dot.offset_left = 9
			dot.offset_top = 9
			dot.offset_right = -9
			dot.offset_bottom = -9
			dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
			p.add_child(dot)
		hud.add_child(p)
		hud_icons[stone] = p
	hud_label = Label.new()
	hud_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hud_label.add_theme_font_size_override("font_size", 17)
	hud_label.add_theme_color_override("font_color", Color.WHITE)
	hud_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	hud_label.add_theme_constant_override("outline_size", 5)
	box.add_child(hud_label)
	refresh()


func have() -> Array:
	return main.stones.collected if main.stones else []


func refresh() -> void:
	var got := have()
	for stone in hud_icons:
		var p: Panel = hud_icons[stone]
		var sb := StyleBoxFlat.new()
		var on: bool = stone in got
		var sel: bool = stone == selected or (selected == "snap" and on)
		sb.bg_color = Color(0, 0, 0, 0.45) if on else Color(0, 0, 0, 0.2)
		sb.set_corner_radius_all(23)
		sb.set_border_width_all(4 if sel else 2)
		sb.border_color = Color.WHITE if sel else (Stones.STONES[stone].color if on else Color(1, 1, 1, 0.15))
		p.add_theme_stylebox_override("panel", sb)
		p.modulate = Color.WHITE if on else Color(1, 1, 1, 0.25)
	var playing: bool = main.play_mode
	hud.get_parent().visible = playing and not main.menu_open()
	if selected == "" or (selected != "snap" and selected not in got):
		hud_label.text = "Find the 6 Infinity Stones!  (9: Gauntlet)" if got.is_empty() else ""
	else:
		hud_label.text = "%s   T: next stone  F: use" % (POWER_TEXT[selected].split(": ")[-1] if selected != "snap" else "THE SNAP")


func got(stone: String) -> void:
	# A new stone: into the Gauntlet it goes (and it's ready to use).
	selected = stone
	main.combat.equip("gauntlet")
	main.refresh_hud()
	refresh()


func show_stones(gauntlet: Node3D) -> void:
	var got := have()
	for stone in Stones.ORDER:
		var n := gauntlet.find_child("Stone_" + stone.capitalize(), true, false) as Node3D
		if n:
			n.visible = stone in got
			if stone == selected and stone in got:
				pulse(n)


func pulse(n: Node3D) -> void:
	var tw := n.create_tween()
	tw.tween_property(n, "scale", Vector3.ONE * 1.5, 0.15)
	tw.tween_property(n, "scale", Vector3.ONE, 0.25)


func next_stone() -> void:
	var got := have()
	if got.is_empty():
		main.banner("Your Gauntlet is empty - find the Infinity Stones!")
		return
	var options: Array = []
	for stone in Stones.ORDER:
		if stone in got:
			options.append(stone)
	if got.size() == Stones.ORDER.size():
		options.append("snap")
	selected = options[(options.find(selected) + 1) % options.size()]
	if main.combat.current != "gauntlet":
		main.combat.equip("gauntlet")
		main.refresh_hud()
	elif main.combat.held:
		show_stones(main.combat.held)
	main.banner(POWER_TEXT[selected])
	refresh()


func use() -> void:
	var got := have()
	if got.is_empty():
		main.banner("Your Gauntlet is empty - find the Infinity Stones! (Ask Nick Fury.)")
		return
	if selected == "" or (selected != "snap" and selected not in got):
		selected = got[-1]
	var now := Time.get_ticks_msec() / 1000.0
	if now < ready_at.get(selected, 0.0):
		main.banner("The %s is charging up..." % ("Gauntlet" if selected == "snap" else Stones.STONES[selected].name))
		return
	ready_at[selected] = now + COOLDOWN[selected]
	call("power_" + selected)
	refresh()


func me() -> Vector3:
	return main.player.global_position + Vector3(0, 0.3, 0)


func baddies(r: float) -> Array:
	var out := []
	for n in get_tree().get_nodes_in_group("npc"):
		if not n.friendly and n.state != "dead" and (n as Node3D).global_position.distance_to(main.player.global_position) < r:
			out.append(n)
	return out


func ring(col: Color, r: float, secs := 0.5) -> void:
	# An expanding glowing ring on the ground.
	var mi := MeshInstance3D.new()
	var tm := TorusMesh.new()
	tm.inner_radius = 0.85
	tm.outer_radius = 1.0
	tm.rings = 48
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = col
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	tm.material = m
	mi.mesh = tm
	add_child(mi)
	mi.global_position = main.player.global_position + Vector3(0, 0.1, 0)
	mi.scale = Vector3.ONE * 0.2
	var tw := create_tween().set_parallel()
	tw.tween_property(mi, "scale", Vector3(r, 1, r), secs).set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	tw.tween_property(m, "albedo_color", Color(col, 0.0), secs)
	tw.chain().tween_callback(mi.queue_free)


func flash_light(col: Color, energy: float, r: float) -> void:
	var l := OmniLight3D.new()
	l.light_color = col
	l.light_energy = energy
	l.omni_range = r
	add_child(l)
	l.global_position = me() + Vector3(0, 0.5, 0)
	create_tween().tween_property(l, "light_energy", 0.0, 0.6).finished.connect(l.queue_free)


func power_space() -> void:
	# Jump through a portal to the spot you're looking at.
	var from: Vector3 = main.cam.global_position
	var dir: Vector3 = -main.cam.global_basis.z
	var q := PhysicsRayQueryParameters3D.create(from, from + dir * 40.0, 1 | 2)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	var to: Vector3
	if hit.is_empty():
		to = main.player.global_position + Vector3(dir.x, 0, dir.z).normalized() * 12.0
	else:
		to = hit.position + (hit.normal as Vector3) * 0.3
	if to.distance_to(main.player.global_position) > 18.0:
		to = main.player.global_position + (to - main.player.global_position).normalized() * 18.0
	if main.stones.inside_field(to) and not main.stones.inside_field(main.player.global_position):
		main.banner("The force field blocks the Space Stone! Go in on foot.")
		return
	main.combat.sparkles(me(), Stones.STONES.space.color, 40, 1.0)
	main.player.global_position = to + Vector3(0, 0.2, 0)
	main.player.velocity = Vector3.ZERO
	main.combat.sparkles(me(), Stones.STONES.space.color, 40, 1.0)
	flash_light(Stones.STONES.space.color, 5.0, 5.0)
	main.play_sfx(main.pop_snd)


func power_mind() -> void:
	ring(Stones.STONES.mind.color, 8.0)
	flash_light(Stones.STONES.mind.color, 4.0, 8.0)
	var n := 0
	for b in baddies(8.0):
		b.charm(15.0)
		n += 1
	main.banner("Mind Stone! %d baddies are on your side now!" % n if n > 0 else "Mind Stone! (Nobody close enough.)")


func power_reality() -> void:
	ring(Stones.STONES.reality.color, 7.0)
	for b in baddies(7.0):
		if b.guard and b.info.get("boss", false):
			b.take_hit(5, Vector3.ZERO)
			continue
		# Pop! Into bubbles and sweets.
		for col: Color in [Color("ff7ab8"), Color("7ad8ff"), Color("ffe066"), Color("9fff8a")]:
			main.combat.sparkles((b as Node3D).global_position + Vector3(0, 0.3, 0), col, 10, 0.9)
		b.hp = 0
		b.poof()
	main.play_sfx(main.pop_snd)


func power_power() -> void:
	ring(Stones.STONES.power.color, 8.0, 0.4)
	flash_light(Stones.STONES.power.color, 9.0, 10.0)
	main.shake = 1.0
	main.play_sfx(main.crash_snd)
	main.combat.sparkles(me(), Stones.STONES.power.color, 60, 2.0)
	for b in baddies(8.0):
		var d: Vector3 = (b as Node3D).global_position - main.player.global_position
		b.take_hit(5, (d.normalized() + Vector3(0, 0.6, 0)) * 9.0)
	for p in main.combat.props_near(main.player.global_position, 8.0):
		var d: Vector3 = (p as Node3D).global_position - main.player.global_position
		(p as RigidBody3D).apply_central_impulse((d.normalized() + Vector3(0, 1.0, 0)) * 7.0)


func power_time() -> void:
	ring(Stones.STONES.time.color, 14.0, 0.8)
	flash_light(Stones.STONES.time.color, 4.0, 10.0)
	for b in baddies(14.0):
		b.freeze(8.0, Stones.STONES.time.color)
	for s in main.combat.foe_shots:
		s.vel = Vector3.ZERO  # blasts stop in mid-air
	main.banner("Time Stone! Everything's frozen - go go go!")


func power_soul() -> void:
	main.hearts = main.MAX_HEARTS
	main.shield_t = 10.0
	ring(Stones.STONES.soul.color, 3.0)
	main.combat.sparkles(me(), Stones.STONES.soul.color, 50, 1.0)
	main.refresh_hud()
	main.banner("Soul Stone! All better - and a golden shield for 10 seconds!")


func power_snap() -> void:
	# *snap*
	main.shake = 1.2
	main.play_sfx(main.crash_snd)
	var white := ColorRect.new()
	white.color = Color(1, 1, 1, 0.9)
	white.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	white.mouse_filter = Control.MOUSE_FILTER_IGNORE
	(hud.get_parent().get_parent() as CanvasLayer).add_child(white)
	create_tween().tween_property(white, "color", Color(1, 1, 1, 0), 1.2).finished.connect(white.queue_free)
	var n := 0
	for b in baddies(80.0):
		n += 1
		var delay := randf_range(0.6, 2.5)
		get_tree().create_timer(delay).timeout.connect(func():
			if is_instance_valid(b) and b.state != "dead":
				main.combat.sparkles((b as Node3D).global_position + Vector3(0, 0.3, 0), Color("c8a070"), 30, 0.8)
				b.hp = 0
				b.poof())
	main.banner("*SNAP!*  %d baddies turned to dust!" % n)
