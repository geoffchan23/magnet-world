extends CharacterBody3D
## A person or creature out in the ruined city.
##
## Friendly ones wander about, wave when you come close and run away if you hit
## them. Aggressive ones chase you when you get near and attack - and fight back
## when you attack them. Everyone gets knocked flying by vehicles, and anyone who
## runs out of health poofs into sparkles (it's a toy world - no blood).
##
## Models follow the explorer convention: rigid parts whose origins sit at the
## joints (Body, Head, ArmL/R, LegL/R, Tail, plus LegL2.., WingL/R, Jaw, Blob...),
## so walking is just swinging those parts.

const LAYER := 128
const GRAVITY := 14.0
const MODEL_SCALE := 0.55

# kind -> how it looks and behaves. "stand_in" is used until its model exists.
# "ranged" ones shoot slow glowing blasts (tiles block them - build cover!).
# "boss" ones guard an Infinity Stone: they stay near it, have a health bar,
# and teleport away when beaten instead of poofing.
const KINDS := {
	"civilian": {"name": "New Yorker", "friendly": true, "hp": 3, "speed": 1.6, "size": 1.0, "stand_in": "npc_survivor"},
	"shield_agent": {"name": "S.H.I.E.L.D. Agent", "friendly": true, "hp": 4, "speed": 1.6, "size": 1.05, "stand_in": "npc_mechanic"},
	"nick_fury": {"name": "Nick Fury", "friendly": true, "hp": 5, "speed": 1.3, "size": 1.1, "stand_in": "npc_trader", "hints": true},
	"lucky": {"name": "Lucky the Pizza Dog", "friendly": true, "hp": 3, "speed": 2.6, "size": 0.7, "stand_in": "npc_dog", "follows": true},
	"chitauri": {"name": "Chitauri", "friendly": false, "hp": 4, "speed": 1.9, "size": 1.05, "stand_in": "npc_raider",
		"damage": 1, "reach": 0.55, "cooldown": 1.1, "ranged": Color("7dffb0")},
	"outrider": {"name": "Outrider", "friendly": false, "hp": 3, "speed": 2.6, "size": 0.85, "stand_in": "npc_mutant_rat",
		"damage": 1, "reach": 0.5, "cooldown": 0.9},
	"symbiote": {"name": "Symbiote", "friendly": false, "hp": 2, "speed": 1.3, "size": 0.8, "stand_in": "npc_slime",
		"damage": 1, "reach": 0.45, "cooldown": 1.2, "hops": true},
	"ultron_sentry": {"name": "Ultron Sentry", "friendly": false, "hp": 6, "speed": 1.4, "size": 1.1, "stand_in": "npc_scrap_robot",
		"damage": 1, "reach": 0.6, "cooldown": 1.5, "ranged": Color("ff4030")},
	"spider_drone": {"name": "Spider Drone", "friendly": false, "hp": 4, "speed": 2.2, "size": 1.0, "stand_in": "npc_spider_bot",
		"damage": 1, "reach": 0.55, "cooldown": 1.0},
	"hydra_agent": {"name": "Hydra Agent", "friendly": false, "hp": 4, "speed": 1.8, "size": 1.0, "stand_in": "npc_raider",
		"damage": 1, "reach": 0.55, "cooldown": 1.1, "ranged": Color("ff5050")},
	# The Black Order and Thanos himself.
	"ebony_maw": {"name": "Ebony Maw", "friendly": false, "hp": 12, "speed": 1.4, "size": 1.15, "stand_in": "npc_trader", "boss": true,
		"damage": 1, "reach": 0.6, "cooldown": 1.2, "ranged": Color("b070ff")},
	"proxima_midnight": {"name": "Proxima Midnight", "friendly": false, "hp": 12, "speed": 2.0, "size": 1.15, "stand_in": "npc_raider", "boss": true,
		"damage": 1, "reach": 0.8, "cooldown": 1.0},
	"corvus_glaive": {"name": "Corvus Glaive", "friendly": false, "hp": 12, "speed": 2.1, "size": 1.15, "stand_in": "npc_raider", "boss": true,
		"damage": 1, "reach": 0.85, "cooldown": 1.0},
	"cull_obsidian": {"name": "Cull Obsidian", "friendly": false, "hp": 16, "speed": 1.5, "size": 1.6, "stand_in": "npc_scrap_robot", "boss": true,
		"damage": 2, "reach": 1.0, "cooldown": 1.6, "slam": true},
	"thanos": {"name": "Thanos", "friendly": false, "hp": 30, "speed": 1.6, "size": 2.0, "stand_in": "npc_scrap_robot", "boss": true,
		"damage": 2, "reach": 1.2, "cooldown": 1.8, "slam": true},
}
const HELLO := ["Hi!", "Avengers assemble!", "My hero!", "Watch out for Thanos!", "Find the Infinity Stones!", "Can I have your autograph?"]

signal defeated(npc)

var main: Node3D
var kind := ""
var info: Dictionary
var hp := 1
var friendly := true
var state := "wander"  # wander, chase, flee, attack, follow, flying, dead
var target_pos := Vector3.ZERO
var think_t := 0.0
var attack_t := 0.0
var hurt_t := 0.0
var flee_t := 0.0
var spin := Vector3.ZERO
var home := Vector3.ZERO
var bubble: Label3D
var tag: Label3D  # bosses: name and health bar
var guard := false  # stays near home (a stone guard)
var freeze_t := 0.0  # frozen by the Time Stone / stuck in webs
var charm_t := 0.0  # Mind Stone: fighting for you for a while
var shoot_t := 0.0

var visual: Node3D
var model: Node3D
var parts := {}  # node name -> {node, rest}
var phase := 0.0
var idle_t := 0.0
var swing_t := 0.0  # > 0 while an attack swing is playing
var wave_t := 0.0


func setup(k: String, at: Vector3) -> void:
	kind = k
	info = KINDS[k]
	hp = info.hp
	friendly = info.friendly
	home = at
	collision_layer = LAYER
	collision_mask = 1 | 2 | 64 | LAYER
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.16 * float(info.size)
	cap.height = 0.55 * float(info.size)
	cs.shape = cap
	cs.position.y = cap.height / 2
	add_child(cs)
	visual = Node3D.new()
	add_child(visual)
	var path := "res://assets/characters/npc_%s.glb" % k
	var stand_in := not ResourceLoader.exists(path)
	if stand_in:
		path = "res://assets/characters/%s.glb" % info.stand_in
	model = (load(path) as PackedScene).instantiate()
	model.scale = Vector3.ONE * MODEL_SCALE * (float(info.size) if stand_in else 1.0)
	guard = info.get("boss", false)
	model.rotation.y = PI  # models face +Z; the visual faces -Z
	visual.add_child(model)
	for n in model.find_children("*", "Node3D", true, false):
		var node := n as Node3D
		if node is MeshInstance3D or node.get_child_count() > 0:
			parts[node.name] = {"node": node, "rest": node.transform}
	bubble = Label3D.new()
	bubble.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	bubble.font_size = 64
	bubble.pixel_size = 0.004
	bubble.outline_size = 14
	bubble.position.y = 0.85 * float(info.size)
	bubble.no_depth_test = true
	bubble.visible = false
	add_child(bubble)
	if info.get("boss", false):
		tag = Label3D.new()
		tag.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		tag.font_size = 48
		tag.pixel_size = 0.004
		tag.outline_size = 12
		tag.modulate = Color("ffd0ff")
		tag.position.y = 1.05 * float(info.size)
		tag.no_depth_test = true
		add_child(tag)
		update_tag()
	position = at
	visual.rotation.y = randf() * TAU
	think_t = randf() * 2.0


func say(text: String, secs := 1.6, col := Color.WHITE) -> void:
	bubble.text = text
	bubble.modulate = col
	bubble.visible = true
	get_tree().create_timer(secs).timeout.connect(func(): if is_instance_valid(bubble): bubble.visible = false)


func _physics_process(delta: float) -> void:
	if state == "dead":
		return
	if state == "flying":
		# Knocked flying: tumble through the air, then poof (or get back up).
		velocity.y -= GRAVITY * delta
		visual.rotation += spin * delta
		var hit := move_and_collide(velocity * delta)
		if hit and velocity.y < 0.0 and hit.get_normal().y > 0.5:
			if hp <= 0:
				poof()
			else:
				state = "flee" if friendly else "chase"
				visual.rotation = Vector3(0, visual.rotation.y, 0)
				velocity = Vector3.ZERO
		if position.y < -30.0:
			queue_free()
		return

	if freeze_t > 0.0:
		# Frozen in time (or stuck in a web): no moving, no hitting.
		freeze_t -= delta
		velocity = Vector3(0, minf(velocity.y, 0.0) - GRAVITY * delta, 0) if not is_on_floor() else Vector3.ZERO
		move_and_slide()
		if freeze_t <= 0.0:
			set_overlay(null)
		return
	if charm_t > 0.0:
		charm_t -= delta
		if charm_t <= 0.0:
			friendly = info.friendly
			say("Huh?", 1.2)
			set_overlay(null)

	var player: Node3D = main.player_body()
	var to_player := player.global_position - global_position
	to_player.y = 0.0
	var dist := to_player.length()
	think_t -= delta
	attack_t -= delta
	hurt_t -= delta
	flee_t -= delta
	shoot_t -= delta
	if charm_t > 0.0:
		# Mind-controlled: go after the nearest baddie instead of you.
		var foe = main.combat.nearest_enemy(global_position, Vector3.FORWARD, 10.0)
		if foe and foe != self:
			to_player = (foe as Node3D).global_position - global_position
			to_player.y = 0.0
			dist = to_player.length()

	# Decide what to do.
	if friendly:
		if flee_t > 0.0:
			state = "flee"
		elif info.get("follows", false) and dist < 12.0 and main.on_foot():
			state = "follow"
		else:
			state = "wander"
		if charm_t > 0.0:
			state = "attack" if dist < float(info.get("reach", 0.5)) + 0.3 else "chase"
			if dist > 10.0:
				state = "follow"
		elif dist < 2.2 and state == "wander" and wave_t <= 0.0 and main.on_foot():
			wave_t = 2.4 if info.get("hints", false) else 1.6
			if info.get("hints", false) and main.stones:
				say(main.stones.hint(global_position), 4.0, Color("ffe066"))
			else:
				say(HELLO[randi() % HELLO.size()])
	elif flee_t > 0.0:
		state = "flee"  # scared off (sirens, horns)
	else:
		var sight := 11.0 if guard else 9.0
		if guard and global_position.distance_to(home) > 10.0:
			state = "home"  # don't wander away from the stone
		elif dist < sight and main.on_foot():
			state = "attack" if dist < float(info.reach) + 0.3 else "chase"
		elif state != "wander" and dist > 14.0:
			state = "wander"
		if info.has("ranged") and state == "chase" and dist < 8.0 and dist > 1.5 and shoot_t <= 0.0 and main.on_foot():
			shoot_t = randf_range(2.2, 3.4)
			swing_t = 0.4
			main.combat.enemy_shot(global_position + Vector3(0, 0.3 * float(info.size), 0), player.global_position + Vector3(0, 0.25, 0), info.ranged)

	var speed: float = info.speed
	var want := Vector3.ZERO
	match state:
		"wander":
			if think_t <= 0.0 or global_position.distance_to(target_pos) < 0.4:
				think_t = randf_range(2.0, 5.0)
				var a := randf() * TAU
				target_pos = home + Vector3(cos(a), 0, sin(a)) * randf_range(0.5, 4.0)
				if randf() < 0.35:
					target_pos = global_position  # stand around for a bit
			want = (target_pos - global_position)
			want.y = 0
			speed *= 0.45
		"follow":
			if dist > 1.4:
				want = to_player
			speed *= 1.2 if dist > 4.0 else 0.8
		"flee":
			want = -to_player
			speed *= 1.5
		"home":
			want = home - global_position
			want.y = 0
			if want.length() < 1.5:
				state = "wander"
		"chase":
			want = to_player
		"attack":
			want = to_player * 0.01  # face them
			if attack_t <= 0.0:
				attack_t = info.cooldown
				swing_t = 0.4
				get_tree().create_timer(0.18).timeout.connect(_strike)

	var dir := want.normalized() if want.length() > 0.05 else Vector3.ZERO
	if info.get("hops", false):
		# Slimes boing along instead of walking.
		if is_on_floor() and dir != Vector3.ZERO and fmod(idle_t, 0.8) < delta:
			velocity.y = 3.2
		if is_on_floor():
			dir *= 0.0 if velocity.y <= 0.0 else 1.0
	var move := dir * speed if state != "attack" else Vector3.ZERO
	velocity.x = move_toward(velocity.x, move.x, 20.0 * delta)
	velocity.z = move_toward(velocity.z, move.z, 20.0 * delta)
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	elif velocity.y < 0.0:
		velocity.y = 0.0
	move_and_slide()
	# Bumped into a wall while wandering? Pick somewhere else.
	if state == "wander" and get_slide_collision_count() > 0 and get_last_slide_collision().get_normal().y < 0.5:
		think_t = 0.0
	if dir.length() > 0.1:
		visual.rotation.y = lerp_angle(visual.rotation.y, atan2(-dir.x, -dir.z), 10.0 * delta)
	if position.y < -30.0:
		queue_free()

	# Run over by whatever the player is driving.
	var v: Node3D = main.driven_vehicle()
	var vv: Vector3 = v.velocity_now() if v else Vector3.ZERO
	if v and vv.length() > 2.5:
		var local := v.global_transform.affine_inverse() * global_position
		var half: Vector3 = v.get_meta("half_size", Vector3(0.6, 0.6, 1.1))
		if absf(local.x) < half.x + 0.15 and absf(local.z) < half.z + 0.15 and local.y > -0.5 and local.y < half.y * 2.0 + 0.3:
			knock(vv * 0.9 + Vector3(0, 5.0, 0), 99 if not friendly else 0)

	animate(delta, Vector2(velocity.x, velocity.z).length())


func _strike() -> void:
	if state == "dead" or state == "flying" or freeze_t > 0.0 or not is_instance_valid(main):
		return
	if charm_t > 0.0:
		var foe = main.combat.nearest_enemy(global_position, Vector3.FORWARD, float(info.get("reach", 0.5)) + 0.6)
		if foe and foe != self:
			foe.take_hit(int(info.get("damage", 1)) + 1, ((foe as Node3D).global_position - global_position).normalized() * 3.0)
		return
	var player: Node3D = main.player_body()
	if info.get("slam", false):
		# Big ones pound the ground: a shockwave you can see.
		main.combat.sparkles(global_position + visual.global_basis.z * -0.6, Color("c9a0ff"), 24, 1.2)
		main.shake = maxf(main.shake, 0.4)
	if global_position.distance_to(player.global_position) < float(info.reach) + 0.45 and main.on_foot():
		main.hurt_player(int(info.damage), global_position)


func take_hit(damage: int, push: Vector3) -> void:
	# Hit by one of your weapons.
	if state == "dead":
		return
	if charm_t > 0.0 and damage > 0:
		return  # it's on your side right now
	hp -= damage
	hurt_t = 0.25
	flash_white()
	update_tag()
	if friendly:
		flee_t = 6.0
		say(["Hey!", "Ouch!", "Leave me alone!", "Eek!"][randi() % 4], 1.4)
	else:
		state = "chase"  # now it's personal
	if guard and hp > 0:
		velocity += push * 0.3  # bosses barely budge
		if randf() < 0.3:
			say(["Hmph!", "You'll pay for that!", "Is that all?", "Grrr!"][randi() % 4], 1.2, Color("e0b0ff"))
	elif hp <= 0 or push.length() > 4.0:
		knock(push + Vector3(0, 3.0 + push.length() * 0.2, 0), 0)
	else:
		velocity += push


func knock(v: Vector3, extra_damage: int) -> void:
	if state == "dead":
		return
	if guard:
		# Too big to run over: hurts them a bit and shoves them back.
		hp -= 2 if extra_damage > 0 else 0
		update_tag()
		velocity = Vector3(v.x, 0, v.z) * 0.3
		if hp <= 0:
			poof()
		return
	hp -= extra_damage
	state = "flying"
	velocity = v
	spin = Vector3(randf_range(-9, 9), randf_range(-6, 6), randf_range(-9, 9))
	main.play_sfx(main.thud_snd)
	if friendly and hp > 0:
		say("Whoaaa!", 1.2)


func flash_white() -> void:
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		var over := StandardMaterial3D.new()
		over.albedo_color = Color(1, 1, 1, 0.7)
		over.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		over.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.material_overlay = over
	get_tree().create_timer(0.12).timeout.connect(func():
		if is_instance_valid(model):
			for mi in model.find_children("*", "MeshInstance3D", true, false):
				(mi as MeshInstance3D).material_overlay = null)


func update_tag() -> void:
	if tag == null:
		return
	var n := 10
	var full := clampi(ceili(float(hp) / float(info.hp) * n), 0, n)
	tag.text = "%s\n%s%s" % [info.name, "■".repeat(full), "□".repeat(n - full)]


func set_overlay(col) -> void:
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var over: StandardMaterial3D = null
		if col != null:
			over = StandardMaterial3D.new()
			over.albedo_color = col
			over.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			over.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		(mi as MeshInstance3D).material_overlay = over


func freeze(secs: float, col: Color) -> void:
	# Time Stone (green) or webbed up (white): stuck where they stand.
	if state == "dead":
		return
	freeze_t = secs
	set_overlay(Color(col, 0.45))


func charm(secs: float) -> void:
	# Mind Stone: this one's on your side for a while.
	if state == "dead" or friendly:
		return
	if guard:
		freeze(3.0, Color("ffe066"))  # bosses just get dizzy
		say("My head...!", 2.0, Color("ffe066"))
		return
	charm_t = secs
	friendly = true
	set_overlay(Color(1.0, 0.9, 0.3, 0.3))
	say("I'm with you now!", 2.0, Color("ffe066"))


func poof() -> void:
	state = "dead"
	collision_layer = 0
	defeated.emit(self)
	if guard:
		# Beaten bosses teleport away in a purple flash - they'll be back another day.
		say(["Impossible!", "This isn't over!", "Retreat!"][randi() % 3], 1.5, Color("e0b0ff"))
		main.sparkle_burst(global_position + Vector3(0, 0.5, 0), Color("b070ff"))
		main.add_stars(10, global_position)
		var tw := create_tween()
		tw.tween_interval(0.6)
		tw.tween_property(visual, "scale", Vector3(0.05, 2.5, 0.05), 0.25)
		tw.tween_callback(queue_free)
		return
	main.sparkle_burst(global_position + Vector3(0, 0.25, 0), Color("fff3a0"))
	main.play_sfx(main.pop_snd)
	if not friendly:
		main.add_stars(1, global_position)
	var tw := create_tween()
	tw.tween_property(visual, "scale", Vector3(1.4, 0.2, 1.4), 0.08)
	tw.tween_property(visual, "scale", Vector3.ONE * 0.01, 0.12)
	tw.tween_callback(queue_free)


# ---------------------------------------------------------------- animation

func pose(part: String, rot: Vector3, offset := Vector3.ZERO) -> void:
	if not parts.has(part):
		return
	var p: Dictionary = parts[part]
	var rest: Transform3D = p.rest
	(p.node as Node3D).transform = Transform3D(rest.basis * Basis.from_euler(rot), rest.origin + offset)


func animate(delta: float, hspeed: float) -> void:
	var moving := clampf(hspeed / maxf(float(info.speed), 0.1), 0.0, 1.0)
	phase += hspeed * delta * 7.0 / float(info.size)
	idle_t += delta
	wave_t -= delta
	swing_t -= delta
	var s := sin(phase) * 0.8 * moving
	var atk := clampf(swing_t / 0.4, 0.0, 1.0)
	var strike := sin(atk * PI)  # 0 -> 1 -> 0 over the swing
	# Legs: Leg<L|R><n>. Two legs walk left/right; four legs walk in diagonal
	# pairs (LegL2 with LegR); spiders (1-4 a side) stride in two alternating
	# groups, swinging sideways-sticking legs about Y and lifting about Z.
	for n in parts:
		var name: String = n
		if name.begins_with("Leg") and name.length() >= 4:
			var left := name[3] == "L"
			var side := 1.0 if left else -1.0
			var idx := name.substr(4).to_int()  # LegL -> 0, LegL2 -> 2
			if parts.has("LegL4"):
				var group := 1.0 if (idx + (0 if left else 1)) % 2 == 1 else -1.0
				var g := sin(phase * 1.4) * group * moving
				pose(name, Vector3(0, g * 0.45, maxf(g, 0.0) * 0.5 * side))
			elif idx == 2:
				pose(name, Vector3(-s * side, 0, 0))  # back legs move with the opposite front leg
			else:
				pose(name, Vector3(s * side, 0, 0))
	for n in parts:
		var name: String = n
		if name.begins_with("Wing"):
			pose(name, Vector3(0, 0, sin(idle_t * 14.0) * 0.5 * (1.0 if name.ends_with("L") else -1.0)))
		elif name.begins_with("Blob"):
			var sq := 1.0 + sin(idle_t * 6.0 + name.hash() % 7) * 0.08
			var p: Dictionary = parts[name]
			(p.node as Node3D).transform = Transform3D((p.rest as Transform3D).basis.scaled(Vector3(1.0 / sq, sq, 1.0 / sq)), (p.rest as Transform3D).origin)
	var wave := clampf(wave_t, 0.0, 1.0) * (0.5 + 0.5 * sin(idle_t * 14.0))
	pose("ArmL", Vector3(-s * 0.9, 0, -0.1 * moving))
	pose("ArmR", Vector3(s * 0.9 - strike * 2.2, 0, 0.1 * moving + wave * 2.6 + (0.4 if wave_t > 0.0 else 0.0)))
	pose("Head", Vector3(-strike * 0.3, 0.15 * sin(idle_t * 0.8) * (1.0 - moving), 0))
	pose("Jaw", Vector3(strike * 0.7 + 0.08 * sin(idle_t * 3.0), 0, 0))
	pose("Tail", Vector3(0, sin(idle_t * (5.0 + 6.0 * moving)) * 0.35, 0))
	pose("Body", Vector3(strike * 0.25, 0, 0.05 * sin(phase) * moving))
	model.position.y = absf(sin(phase)) * 0.03 * moving
	if info.get("hops", false):
		var sq := 1.0 + clampf(-velocity.y * 0.05, -0.25, 0.25)
		visual.scale = Vector3(1.0 / sqrt(sq), sq, 1.0 / sqrt(sq))
	elif hurt_t > 0.0:
		visual.scale = Vector3(1.15, 0.85, 1.15)
	else:
		visual.scale = Vector3.ONE
