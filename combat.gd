extends Node3D
## Weapons, attacks, projectiles and explosions (explore mode).
##
## Number keys pick a weapon; F (or a left click) attacks. Melee weapons hit
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
}
const ORDER := ["fists", "sword", "knife", "bat", "hammer", "blaster", "bow", "rocket"]
# Model names inside assets/weapons/weapons.glb.
const MESH := {"sword": "Sword", "knife": "Knife", "bat": "Bat", "hammer": "Hammer", "blaster": "Blaster", "bow": "Bow", "rocket": "RocketLauncher"}

var main: Node3D
var current := "fists"
var cooldown := 0.0
var held: Node3D  # the weapon model in the explorer's hand
var kit := {}  # mesh name -> Node3D template
var shots: Array = []  # {node, vel, kind, damage, life, drop}
var sparkle_mat: StandardMaterial3D


func _ready() -> void:
	var path := "res://assets/weapons/weapons.glb"
	if ResourceLoader.exists(path):
		var scene: Node3D = (load(path) as PackedScene).instantiate()
		for n in scene.get_children():
			kit[(n as Node).name] = n
		add_child(scene)
		scene.visible = false


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
	main.play_sfx(main.click_snd)


func attack() -> void:
	if cooldown > 0.0 or main.busy:
		return
	var w: Dictionary = WEAPONS[current]
	cooldown = w.cooldown
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
			hit_any = true
	# Melee also bonks the loose junk around.
	for b in props_near(p + fwd * 0.5, float(w.reach)):
		(b as RigidBody3D).apply_central_impulse(fwd * float(w.push) * 0.6 + Vector3(0, 1.5, 0))
		hit_any = true
	if w.get("slam", false):
		main.shake = 0.5
		sparkles(p + fwd * 0.7, Color("ffe7a0"), 18)
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
		"bolt":
			node = MeshInstance3D.new()
			var cap := CapsuleMesh.new()
			cap.radius = 0.035
			cap.height = 0.28
			var m := StandardMaterial3D.new()
			m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			m.albedo_color = Color("7ff0ff")
			m.emission_enabled = true
			m.emission = Color("40e0ff")
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
				elif c is RigidBody3D:
					(c as RigidBody3D).apply_central_impulse((s.vel as Vector3).normalized() * 1.5)
				sparkles(at, Color("7ff0ff") if w.shot == "bolt" else Color("ffe7a0"), 6, 0.4)
				if w.shot == "arrow" and c and not c.is_in_group("npc"):
					node.global_position = at  # it sticks, then fades away
					get_tree().create_timer(4.0).timeout.connect(node.queue_free)
				else:
					node.queue_free()
			continue
		node.global_position = to
		node.look_at(to + s.vel, Vector3.UP, true)


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
		if n.friendly or n.state == "dead":
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
