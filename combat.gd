extends Node3D
## Weapons, attacks, projectiles and explosions (explore mode).
##
## Number keys pick a weapon; F (or a left click) attacks. Slot 1 is your
## hero's own move (Spidey's webs, Cap's shield, Thor's hammer...), slot 9 is
## the Infinity Gauntlet (powers.gd). Melee weapons hit
## whatever is in front of you; ranged ones auto-aim at the nearest baddie in
## front so it's easy for small hands. Rockets explode: they knock everything
## around flying and will even smash your build.

const Rides := preload("res://rides.gd")
const WEAPONS := {
	"fists": {"name": "Fists", "melee": true, "damage": 1, "reach": 0.55, "arc": 1.2, "cooldown": 0.35, "push": 2.0},
	"sword": {"name": "Sword", "melee": true, "damage": 2, "reach": 0.85, "arc": 1.6, "cooldown": 0.45, "push": 3.0},
	"knife": {"name": "Knife", "melee": true, "damage": 1, "reach": 0.6, "arc": 1.0, "cooldown": 0.22, "push": 1.5},
	"bat": {"name": "Bat", "melee": true, "damage": 2, "reach": 0.8, "arc": 1.8, "cooldown": 0.55, "push": 7.0},
	"hammer": {"name": "Hammer", "melee": true, "damage": 4, "reach": 0.9, "arc": 2.4, "cooldown": 0.9, "push": 9.0, "slam": true},
	"blaster": {"name": "Blaster", "melee": false, "damage": 1, "cooldown": 0.22, "speed": 26.0, "shot": "bolt"},
	"bow": {"name": "Bow & Arrow", "melee": false, "damage": 2, "cooldown": 0.6, "speed": 20.0, "shot": "arrow", "drop": 6.0},
	"rocket": {"name": "Rocket Launcher", "melee": false, "damage": 4, "cooldown": 1.2, "speed": 14.0, "shot": "rocket", "boom": 2.6},
	"gauntlet": {"name": "Infinity Gauntlet", "melee": false, "gauntlet": true, "cooldown": 0.8},
}
const ORDER := ["fists", "sword", "knife", "bat", "hammer", "blaster", "bow", "rocket", "gauntlet"]
# Model names inside assets/weapons/weapons.glb and gear.glb.
const MESH := {"sword": "Sword", "knife": "Knife", "bat": "Bat", "hammer": "Hammer", "blaster": "Blaster", "bow": "Bow", "rocket": "RocketLauncher", "gauntlet": "Gauntlet"}
# Each hero's own move, in slot 1 instead of fists.
const HERO_MOVES := {
	"spider_man": {"name": "Web Shooter", "melee": false, "damage": 1, "cooldown": 0.35, "speed": 20.0, "shot": "web", "color": Color("ffffff"), "stun": 2.5},
	"iron_man": {"name": "Repulsor Blast", "melee": false, "damage": 2, "cooldown": 0.4, "speed": 28.0, "shot": "bolt", "color": Color("ffe2b0")},
	"captain_america": {"name": "Shield Throw", "melee": false, "damage": 2, "cooldown": 0.9, "speed": 13.0, "shot": "boomerang", "model": "CapShield", "color": Color("9fc8ff")},
	"thor": {"name": "Mjolnir Throw", "melee": false, "damage": 3, "cooldown": 1.0, "speed": 13.0, "shot": "boomerang", "model": "Mjolnir", "color": Color("a0d8ff"), "zap": true},
	"hulk": {"name": "Hulk Smash", "melee": true, "damage": 4, "reach": 1.1, "arc": 3.2, "cooldown": 0.8, "push": 10.0, "slam": true, "color": Color("9fe070")},
	"black_widow": {"name": "Widow's Bite", "melee": true, "damage": 2, "reach": 0.7, "arc": 1.6, "cooldown": 0.35, "push": 3.0, "color": Color("7fd0ff"), "stun": 1.5},
	"hawkeye": {"name": "Trick Arrow", "melee": false, "damage": 2, "cooldown": 0.6, "speed": 20.0, "shot": "arrow", "drop": 6.0, "boom": 1.3},
	"black_panther": {"name": "Vibranium Claws", "melee": true, "damage": 2, "reach": 0.75, "arc": 2.2, "cooldown": 0.3, "push": 3.0, "color": Color("c090ff")},
	"doctor_strange": {"name": "Mystic Bolt", "melee": false, "damage": 2, "cooldown": 0.45, "speed": 18.0, "shot": "bolt", "color": Color("ffa040")},
	"captain_marvel": {"name": "Photon Blast", "melee": false, "damage": 3, "cooldown": 0.5, "speed": 26.0, "shot": "bolt", "color": Color("ffd060")},
	"scarlet_witch": {"name": "Hex Bolt", "melee": false, "damage": 2, "cooldown": 0.4, "speed": 16.0, "shot": "bolt", "color": Color("ff3050")},
	"vision": {"name": "Mind Beam", "melee": false, "damage": 2, "cooldown": 0.4, "speed": 30.0, "shot": "bolt", "color": Color("ffe040")},
	"ant_man": {"name": "Giant Punch", "melee": true, "damage": 3, "reach": 0.8, "arc": 1.6, "cooldown": 0.5, "push": 9.0, "color": Color("ff6060")},
	"wasp": {"name": "Wasp Sting", "melee": false, "damage": 1, "cooldown": 0.18, "speed": 24.0, "shot": "bolt", "color": Color("ffe060")},
	"falcon": {"name": "Redwing Blaster", "melee": false, "damage": 1, "cooldown": 0.25, "speed": 24.0, "shot": "bolt", "color": Color("ff5040")},
	"war_machine": {"name": "Mini-Gun", "melee": false, "damage": 1, "cooldown": 0.12, "speed": 30.0, "shot": "bolt", "color": Color("ffe0a0")},
	"winter_soldier": {"name": "Metal Arm Punch", "melee": true, "damage": 3, "reach": 0.7, "arc": 1.4, "cooldown": 0.45, "push": 8.0, "color": Color("d0e0ff")},
}

var main: Node3D
var current := "fists"
var cooldown := 0.0
var held: Node3D  # the weapon model in the explorer's hand
var kit := {}  # mesh name -> Node3D template
var shots: Array = []  # {node, vel, kind, damage, life, drop}
var foe_shots: Array = []  # baddies' blasts: {node, vel, life}
var sparkle_mat: StandardMaterial3D


func _ready() -> void:
	for path in ["res://assets/weapons/weapons.glb", "res://assets/weapons/gear.glb"]:
		if ResourceLoader.exists(path):
			var scene: Node3D = (load(path) as PackedScene).instantiate()
			for n in scene.get_children():
				kit[(n as Node).name] = n
			add_child(scene)
			scene.visible = false


func weapon_info(w: String) -> Dictionary:
	# Slot 1 is whatever your hero does best.
	if w == "fists":
		return HERO_MOVES.get(main.player.character, WEAPONS.fists)
	return WEAPONS[w]


func model_of(name: String) -> Node3D:
	if kit.has(name):
		var m := (kit[name] as Node3D).duplicate() as Node3D
		m.transform = Transform3D.IDENTITY
		m.visible = true
		return m
	# Stand-in until the Blender weapons exist.
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	var mat := StandardMaterial3D.new()
	match name:
		"Arrow":
			box.size = Vector3(0.02, 0.02, 0.35)
			mat.albedo_color = Color("c8a060")
		"Rocket":
			box.size = Vector3(0.07, 0.07, 0.25)
			mat.albedo_color = Color("d04030")
		"Hammer":
			box.size = Vector3(0.12, 0.12, 0.45)
			mat.albedo_color = Color("777777")
		_:
			box.size = Vector3(0.04, 0.04, 0.35)
			mat.albedo_color = Color("b0b8c0")
	box.material = mat
	mi.mesh = box
	mi.position.z = box.size.z / 2
	var root := Node3D.new()
	root.add_child(mi)
	return root


func equip(w: String) -> void:
	current = w
	if held:
		held.queue_free()
		held = null
	var hand: Node3D = main.player.hand()
	if hand == null or not MESH.has(w):
		return
	held = model_of(MESH[w])
	hand.add_child(held)
	# The hand node lives inside the 0.55-scaled toy model; weapons are modelled at world size.
	held.scale = Vector3.ONE / main.player.MODEL_SCALE
	if w == "gauntlet" and main.powers:
		main.powers.show_stones(held)
	main.play_sfx(main.click_snd)


func attack() -> void:
	if cooldown > 0.0 or main.busy:
		return
	var w: Dictionary = weapon_info(current)
	cooldown = w.cooldown
	if w.get("gauntlet", false):
		main.player.swing(0.4, current)
		main.powers.use()
		return
	var p: CharacterBody3D = main.player
	var fwd: Vector3 = p.facing()
	var target = nearest_enemy(p.global_position, fwd, 16.0 if not w.melee else 2.2)
	if target:
		var to: Vector3 = (target.global_position - p.global_position)
		to.y = 0
		fwd = to.normalized()
		p.face(fwd)
		if w.melee and to.length() > float(w.reach):
			p.velocity += fwd * minf((to.length() - float(w.reach) * 0.7) * 6.0, 7.0)  # lunge at it
			p.hurt_t = maxf(p.hurt_t, 0.15)  # (lets the lunge slide instead of being overwritten by walking)
	p.swing(0.35 if w.melee else 0.25, current)
	if w.melee:
		get_tree().create_timer(0.12).timeout.connect(func(): melee_hit(w, fwd))
	else:
		launch(w, fwd, target)


func melee_hit(w: Dictionary, fwd: Vector3) -> void:
	var p: Vector3 = main.player.global_position
	var hit_any := false
	for n in get_tree().get_nodes_in_group("npc"):
		var npc := n as Node3D
		var d := npc.global_position - p
		d.y = 0
		if d.length() < float(w.reach) + 0.25 and (d.length() < 0.25 or fwd.angle_to(d.normalized()) < float(w.arc) / 2):
			npc.take_hit(int(w.damage), fwd * float(w.push) + Vector3(0, 1.0, 0))
			if w.has("stun") and npc.state != "dead":
				npc.freeze(float(w.stun), Color("bfe8ff"))
			if w.has("color"):
				sparkles(npc.global_position + Vector3(0, 0.3, 0), w.color, 14, 0.6)
			hit_any = true
	# Melee also bonks the loose junk around.
	for b in props_near(p + fwd * 0.5, float(w.reach)):
		(b as RigidBody3D).apply_central_impulse(fwd * float(w.push) * 0.6 + Vector3(0, 1.5, 0))
		hit_any = true
	if w.get("slam", false):
		main.shake = 0.5
		sparkles(p + fwd * 0.7, w.get("color", Color("ffe7a0")), 18)
	if hit_any:
		main.play_sfx(main.thud_snd)


func launch(w: Dictionary, fwd: Vector3, target) -> void:
	var p: CharacterBody3D = main.player
	var from: Vector3 = p.global_position + Vector3(0, 0.32, 0) + fwd * 0.3
	var vel := fwd * float(w.speed)
	if target:
		# Aim at its middle (and lob arrows a little).
		var aim: Vector3 = (target as Node3D).global_position + Vector3(0, 0.22, 0)
		var t := from.distance_to(aim) / float(w.speed)
		vel = (aim - from) / t + Vector3(0, 0.5 * float(w.get("drop", 0.0)) * t, 0)
	var node: Node3D
	match w.shot:
		"boomerang":
			node = Node3D.new()
			var m := model_of(w.model)
			node.add_child(m)
			m.name = "Spin"
			add_child(node)
			node.global_position = from
			var out := (target as Node3D).global_position + Vector3(0, 0.25, 0) if target else from + fwd * 7.0
			shots.append({"node": node, "w": w, "life": 4.0, "boomerang": true, "out": out, "back": false, "hit": []})
			main.play_sfx(main.click_snd)
			return
		"bolt", "web":
			node = MeshInstance3D.new()
			var cap := CapsuleMesh.new()
			cap.radius = 0.035
			cap.height = 0.28
			var m := StandardMaterial3D.new()
			m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			var col: Color = w.get("color", Color("7ff0ff"))
			m.albedo_color = col.lightened(0.4)
			m.emission_enabled = true
			m.emission = col
			m.emission_energy_multiplier = 4.0
			cap.material = m
			(node as MeshInstance3D).mesh = cap
			(node as MeshInstance3D).rotation.x = PI / 2
			var holder := Node3D.new()
			holder.add_child(node)
			node = holder
		"arrow":
			node = model_of("Arrow")
		"rocket":
			node = model_of("Rocket")
	add_child(node)
	node.global_position = from
	node.look_at(from + vel, Vector3.UP, true)
	shots.append({"node": node, "vel": vel, "w": w, "life": 3.0})
	main.play_sfx(main.click_snd)


func _physics_process(delta: float) -> void:
	cooldown -= delta
	var space := get_world_3d().direct_space_state
	for s in shots.duplicate():
		var node: Node3D = s.node
		var w: Dictionary = s.w
		s.life -= delta
		if s.get("boomerang", false):
			fly_boomerang(s, delta)
			continue
		s.vel += Vector3(0, -float(w.get("drop", 0.0)), 0) * delta
		var from := node.global_position
		var to: Vector3 = from + s.vel * delta
		var q := PhysicsRayQueryParameters3D.create(from, to, 1 | 2 | 64 | 128)
		var hit := space.intersect_ray(q)
		if w.shot == "rocket" and randf() < 0.8:
			sparkles(from, Color("ffb050"), 1, 0.3)
		if not hit.is_empty() or s.life <= 0.0:
			shots.erase(s)
			var at: Vector3 = hit.position if not hit.is_empty() else to
			if w.has("boom"):
				explode(at, float(w.boom), int(w.damage))
				node.queue_free()
			else:
				var c: Object = hit.get("collider")
				if c and c.is_in_group("npc"):
					c.take_hit(int(w.damage), (s.vel as Vector3).normalized() * 2.0)
					if w.has("stun") and c.state != "dead":
						c.freeze(float(w.stun), Color("ffffff"))  # webbed up!
				elif c is RigidBody3D:
					(c as RigidBody3D).apply_central_impulse((s.vel as Vector3).normalized() * 1.5)
				sparkles(at, w.get("color", Color("7ff0ff")) if w.shot != "arrow" else Color("ffe7a0"), 6, 0.4)
				if w.shot == "arrow" and c and not c.is_in_group("npc"):
					node.global_position = at  # it sticks, then fades away
					get_tree().create_timer(4.0).timeout.connect(node.queue_free)
				else:
					node.queue_free()
			continue
		node.global_position = to
		node.look_at(to + s.vel, Vector3.UP, true)
	fly_foe_shots(delta)


func fly_boomerang(s: Dictionary, delta: float) -> void:
	# Cap's shield and Mjolnir: fly out, bonk everything on the way, come back to your hand.
	var node: Node3D = s.node
	var w: Dictionary = s.w
	var home: Vector3 = main.player.global_position + Vector3(0, 0.3, 0)
	var goal: Vector3 = home if s.back else s.out
	var step := float(w.speed) * delta * (1.3 if s.back else 1.0)
	var to_goal := goal - node.global_position
	if to_goal.length() <= step or s.life <= 0.0:
		if s.back or s.life <= 0.0:
			shots.erase(s)
			node.queue_free()
			return
		s.back = true
	else:
		node.global_position += to_goal.normalized() * step
	(node.get_node("Spin") as Node3D).rotate_y(delta * 22.0)
	for n in get_tree().get_nodes_in_group("npc"):
		if n in s.hit or n.friendly or n.state == "dead":
			continue
		if (n as Node3D).global_position.distance_to(node.global_position - Vector3(0, 0.25, 0)) < 0.5:
			s.hit.append(n)
			n.take_hit(int(w.damage), to_goal.normalized() * 3.0 + Vector3(0, 1.0, 0))
			sparkles(node.global_position, w.color, 16, 0.6)
			if w.get("zap", false):
				zap(node.global_position)
			main.play_sfx(main.thud_snd)
			s.back = true


func zap(at: Vector3) -> void:
	# A crack of Thor's lightning.
	sparkles(at + Vector3(0, 1.2, 0), Color("cfe8ff"), 30, 1.4)
	var flash := OmniLight3D.new()
	flash.light_color = Color("a8d0ff")
	flash.light_energy = 6.0
	flash.omni_range = 5.0
	add_child(flash)
	flash.global_position = at + Vector3(0, 1.0, 0)
	create_tween().tween_property(flash, "light_energy", 0.0, 0.3).finished.connect(flash.queue_free)


func enemy_shot(from: Vector3, at: Vector3, col: Color) -> void:
	# A slow glowing blast from a baddie or a turret: dodge it, or hide behind your tiles.
	var mi := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.07
	sm.height = 0.14
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = col.lightened(0.5)
	m.emission_enabled = true
	m.emission = col
	m.emission_energy_multiplier = 3.0
	sm.material = m
	mi.mesh = sm
	add_child(mi)
	mi.global_position = from
	var light := OmniLight3D.new()
	light.light_color = col
	light.light_energy = 1.2
	light.omni_range = 1.2
	mi.add_child(light)
	foe_shots.append({"node": mi, "vel": (at - from).normalized() * 7.0, "life": 2.5, "col": col})


func fly_foe_shots(delta: float) -> void:
	var space := get_world_3d().direct_space_state
	for s in foe_shots.duplicate():
		var node: Node3D = s.node
		s.life -= delta
		var from := node.global_position
		var to: Vector3 = from + s.vel * delta
		var q := PhysicsRayQueryParameters3D.create(from, to, 1 | 2 | 4)
		var hit := space.intersect_ray(q)
		var pd: Vector3 = main.player.global_position + Vector3(0, 0.25, 0) - to
		if pd.length() < 0.3 and main.on_foot():
			main.hurt_player(1, from)
			hit = {"position": to}
		if not hit.is_empty() or s.life <= 0.0:
			sparkles(hit.get("position", to), s.col, 10, 0.4)
			foe_shots.erase(s)
			node.queue_free()
			continue
		node.global_position = to


func explode(at: Vector3, radius: float, damage: int) -> void:
	main.shake = 0.9
	main.play_sfx(main.crash_snd)
	sparkles(at, Color("ffa040"), 40, 1.0)
	sparkles(at, Color("fff0a0"), 20, 0.6)
	var flash := OmniLight3D.new()
	flash.light_color = Color("ffb060")
	flash.light_energy = 8.0
	flash.omni_range = radius * 3.0
	add_child(flash)
	flash.global_position = at + Vector3(0, 0.5, 0)
	create_tween().tween_property(flash, "light_energy", 0.0, 0.4).finished.connect(flash.queue_free)
	for n in get_tree().get_nodes_in_group("npc"):
		var d := (n as Node3D).global_position - at
		if d.length() < radius:
			n.take_hit(0 if n.friendly else damage, (d.normalized() + Vector3(0, 0.8, 0)) * 8.0)
	for b in props_near(at, radius):
		var d := (b as Node3D).global_position - at
		(b as RigidBody3D).apply_central_impulse((d.normalized() + Vector3(0, 1.0, 0)) * 6.0)
	# Rockets smash builds too (Z puts them back).
	for t in main.tiles:
		if (t.xform.origin as Vector3).distance_to(at) < radius:
			main.destroyer.shatter(at, Vector3.ZERO, 5.0, radius * 1.5)
			break
	var pd: Vector3 = main.player.global_position - at
	if pd.length() < radius * 0.7 and main.on_foot():
		main.player.velocity += (pd.normalized() + Vector3(0, 1.2, 0)) * 4.0


func nearest_enemy(from: Vector3, fwd: Vector3, reach: float):
	# The closest baddie, preferring ones in front of you (any direction counts).
	var best = null
	var best_d := INF
	for n in get_tree().get_nodes_in_group("npc"):
		if n.friendly or n.state == "dead" or (n as Node3D).global_position.distance_to(from) < 0.05:
			continue
		var d := (n as Node3D).global_position - from
		d.y = 0
		if d.length() > reach:
			continue
		var score := d.length() * (1.0 + fwd.angle_to(d.normalized()) * 0.5)
		if score < best_d:
			best = n
			best_d = score
	return best


func props_near(at: Vector3, r: float) -> Array:
	var shape := SphereShape3D.new()
	shape.radius = r
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.transform = Transform3D(Basis(), at)
	q.collision_mask = 64 | 8
	var out := []
	for h in get_world_3d().direct_space_state.intersect_shape(q, 32):
		if h.collider is RigidBody3D:
			out.append(h.collider)
	return out


func sparkles(at: Vector3, col: Color, amount := 24, scale := 1.0) -> void:
	# A quick burst of glowing bits (hits, poofs, explosions).
	var p := CPUParticles3D.new()
	p.one_shot = true
	p.amount = amount
	p.lifetime = 0.6
	p.explosiveness = 1.0
	p.direction = Vector3.UP
	p.spread = 180.0
	p.initial_velocity_min = 1.5 * scale
	p.initial_velocity_max = 4.0 * scale
	p.gravity = Vector3(0, -6, 0)
	p.scale_amount_min = 0.5
	p.scale_amount_max = 1.2
	var q := QuadMesh.new()
	q.size = Vector2(0.07, 0.07) * maxf(scale, 0.5)
	if sparkle_mat == null:
		sparkle_mat = StandardMaterial3D.new()
		sparkle_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		sparkle_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		sparkle_mat.albedo_texture = Rides.soft_dot()
		sparkle_mat.vertex_color_use_as_albedo = true
		sparkle_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	q.material = sparkle_mat
	p.mesh = q
	var grad := Gradient.new()
	grad.set_color(0, col)
	grad.set_color(1, Color(col, 0.0))
	p.color_ramp = grad
	add_child(p)
	p.global_position = at
	p.emitting = true
	p.finished.connect(p.queue_free)
