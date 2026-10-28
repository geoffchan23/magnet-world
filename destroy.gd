extends Node3D
## The Smash! show: a giant or a crane's wrecking ball wrecks everything you built.
##
## At the moment of impact every tile becomes a real physics piece: the ones near
## the hit get flung away, the rest collapse and tumble. The smashers carry
## kinematic "hitter" bodies so they keep shoving debris as they move through.
## Undo (Z) rebuilds the whole structure.

const DEBRIS_LAYER := 8
const HITTER_LAYER := 16
const DEBRIS_LIFETIME := 14.0

var main: Node3D
var running := false
var forced_attack := ""  # testing: "giant:kick" etc. picks the attack instead of random
var debris: Array = []  # RigidBody3D pieces still around
var hitters: Array = []  # [AnimatableBody3D, Callable returning its world position]

# Structure being smashed.
var centre := Vector3.ZERO
var height := 1.0
var radius := 1.0


func start(kind: String) -> void:
	if running:
		return
	if main.tiles.is_empty():
		main.flash("Build something first - then smash it!")
		return
	if kind.begins_with("giant:"):
		forced_attack = kind.substr(6)
		kind = "giant"
	running = true
	measure()
	main.busy = true
	if kind == "giant":
		await giant_show()
	else:
		await ball_show()
	main.busy = false
	running = false


func measure() -> void:
	var lo := Vector3(INF, INF, INF)
	var hi := Vector3(-INF, -INF, -INF)
	for t in main.tiles:
		for p in t.verts:
			lo = lo.min(p)
			hi = hi.max(p)
	centre = Vector3((lo.x + hi.x) / 2, 0, (lo.z + hi.z) / 2)
	height = maxf(hi.y, 0.5)
	radius = maxf(Vector2(hi.x - lo.x, hi.z - lo.z).length() / 2, 0.6)


func frame_camera(look_dir: Vector3, dist: float, look_height: float) -> void:
	# Camera looks across the action from the side.
	var side := Vector3(-look_dir.z, 0, look_dir.x)
	main.cam_yaw = atan2(side.x, side.z)
	main.cam_pitch = 0.3
	main.cam_dist = dist
	main.cam_target = centre + Vector3(0, look_height, 0)


# ---------------------------------------------------------------- shattering

func shatter(impact: Vector3, push: Vector3, strength: float, reach: float) -> void:
	# Turn every tile into a flying piece; record the whole structure for undo.
	var snapshot: Array = []
	for t in main.tiles:
		snapshot.append({"shape": t.shape, "color": t.color, "xform": t.xform})
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	for t in main.tiles.duplicate():
		var xf: Transform3D = t.xform
		var body := RigidBody3D.new()
		body.collision_layer = DEBRIS_LAYER
		body.collision_mask = 1 | 2 | DEBRIS_LAYER | HITTER_LAYER | 32 | 64  # + the buggy and loose junk
		body.mass = 0.4
		var phys := PhysicsMaterial.new()
		phys.bounce = 0.25
		phys.friction = 0.7
		body.physics_material_override = phys
		var old: Node3D = t.node
		# Re-use the tile's visuals and collision shape.
		for c in old.get_children():
			old.remove_child(c)
			body.add_child(c)
		main.remove_tile(t, false, true)
		main.add_child(body)
		body.global_transform = xf
		var d := xf.origin - impact
		var near := clampf(1.0 - d.length() / reach, 0.0, 1.0)
		var away := (d + Vector3(0, 0.9, 0)).normalized()
		var power := strength * 1.8  # everything should really FLY
		var v := away * power * (0.3 + near) + push * (0.4 + near)
		v += Vector3(rng.randf_range(-1, 1), rng.randf_range(0.3, 1.6), rng.randf_range(-1, 1)) * power * 0.35
		body.linear_velocity = v
		body.angular_velocity = Vector3(rng.randf_range(-1, 1), rng.randf_range(-1, 1), rng.randf_range(-1, 1)) * (4.0 + 10.0 * near)
		debris.append({"body": body, "born": Time.get_ticks_msec()})
	main.undo_stack.append({"op": "destroy", "tiles": snapshot})
	main.save_world()
	main.play_sfx(main.crash_snd)
	main.shake = 1.0


func clear_debris() -> void:
	for d in debris:
		if is_instance_valid(d.body):
			(d.body as Node).queue_free()
	debris.clear()


func _physics_process(_delta: float) -> void:
	for h in hitters:
		if is_instance_valid(h[0]):
			(h[0] as AnimatableBody3D).global_position = (h[1] as Callable).call()
	# Tidy up: pieces fade away after a while or once they fall into the clouds.
	var now := Time.get_ticks_msec()
	for d in debris.duplicate():
		var b: RigidBody3D = d.body
		if not is_instance_valid(b):
			debris.erase(d)
		elif b.global_position.y < -40.0:
			b.queue_free()
			debris.erase(d)
		elif now - d.born > DEBRIS_LIFETIME * 1000.0 and not d.has("fading"):
			d.fading = true
			var tw := create_tween()
			for c in b.get_children():
				if c is Node3D:
					tw.parallel().tween_property(c, "scale", Vector3.ONE * 0.01, 0.8)
			tw.tween_callback(b.queue_free)


func add_hitter(r: float, where: Callable) -> AnimatableBody3D:
	var h := AnimatableBody3D.new()
	h.collision_layer = HITTER_LAYER
	h.collision_mask = 0
	var cs := CollisionShape3D.new()
	var sp := SphereShape3D.new()
	sp.radius = r
	cs.shape = sp
	h.add_child(cs)
	add_child(h)
	h.global_position = where.call()
	hitters.append([h, where])
	return h


func clear_hitters() -> void:
	for h in hitters:
		if is_instance_valid(h[0]):
			(h[0] as Node).queue_free()
	hitters.clear()


func wait(t: float) -> void:
	await get_tree().create_timer(t).timeout


func tween_value(from: float, to: float, dur: float, setter: Callable, trans := Tween.TRANS_SINE, ease := Tween.EASE_IN_OUT) -> void:
	var tw := create_tween()
	tw.tween_method(setter, from, to, dur).set_trans(trans).set_ease(ease)
	await tw.finished


# ---------------------------------------------------------------- the giant

var giant: Node3D
var gparts := {}  # name -> {node, rest}


func make_giant(size: float) -> Node3D:
	# Uses the Blender giant if it exists, otherwise a simple stand-in.
	var root := Node3D.new()
	var model: Node3D
	var path := "res://assets/characters/giant.glb"
	if ResourceLoader.exists(path):
		model = (load(path) as PackedScene).instantiate()
	else:
		model = stand_in_giant()
	var box := AABB()
	var first := true
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var b := local_xform(model, mi as Node3D) * (mi as MeshInstance3D).get_aabb()
		box = b if first else box.merge(b)
		first = false
	model.scale = Vector3.ONE * size / maxf(box.size.y, 0.01)
	model.rotation.y = PI  # face -Z like the explorers
	root.add_child(model)
	gparts.clear()
	grot.clear()
	lean_xf = Transform3D()
	for n in ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR"]:
		var node := model.find_child(n, true, false) as Node3D
		if node:
			gparts[n] = {"node": node, "rest": node.transform}
	return root


static func local_xform(root: Node3D, n: Node3D) -> Transform3D:
	# n's transform relative to root (works before anything is in the scene tree).
	var xf := Transform3D()
	while n != root and n != null:
		xf = n.transform * xf
		n = n.get_parent() as Node3D
	return xf


func stand_in_giant() -> Node3D:
	# Capsule giant with the same part names and joint pivots as the real one.
	var m := Node3D.new()
	var skin := StandardMaterial3D.new()
	skin.albedo_color = Color("7fb069")
	var cloth := StandardMaterial3D.new()
	cloth.albedo_color = Color("8d5a3b")
	var defs := {
		"Body": [Vector3(0, 0, 0), Vector3(0, 1.15, 0), 0.42, 0.9, cloth],
		"Head": [Vector3(0, 1.62, 0), Vector3(0, 0.25, 0), 0.3, 0.6, skin],
		"ArmL": [Vector3(-0.52, 1.5, 0), Vector3(0, -0.45, 0), 0.14, 0.95, skin],
		"ArmR": [Vector3(0.52, 1.5, 0), Vector3(0, -0.45, 0), 0.14, 0.95, skin],
		"LegL": [Vector3(-0.2, 0.75, 0), Vector3(0, -0.38, 0), 0.17, 0.8, cloth],
		"LegR": [Vector3(0.2, 0.75, 0), Vector3(0, -0.38, 0), 0.17, 0.8, cloth],
	}
	for n in defs:
		var d: Array = defs[n]
		var mi := MeshInstance3D.new()
		mi.name = n
		var cap := CapsuleMesh.new()
		cap.radius = d[2]
		cap.height = d[3]
		mi.mesh = cap
		mi.material_override = d[4]
		mi.position = d[0]
		m.add_child(mi)
		var shape := MeshInstance3D.new()
		shape.mesh = cap
		shape.material_override = d[4]
		mi.mesh = null
		shape.position = d[1]
		mi.add_child(shape)
		var holder := MeshInstance3D.new()  # keeps get_aabb() meaningful for sizing
		holder.mesh = cap
		holder.visible = false
		holder.position = d[1] + d[0]
		m.add_child(holder)
	return m


const UPPER := ["Body", "Head", "ArmL", "ArmR"]
var lean_xf := Transform3D()  # upper-body bend, around the hips
var grot := {}  # current rotation of each part


func gpose(part: String, rot: Vector3) -> void:
	if not gparts.has(part):
		return
	grot[part] = rot
	var p: Dictionary = gparts[part]
	var rest: Transform3D = p.rest
	var xf := Transform3D(rest.basis * Basis.from_euler(rot), rest.origin)
	if part in UPPER:
		xf = lean_xf * xf
	(p.node as Node3D).transform = xf


func set_lean(rot: Vector3) -> void:
	# Bend the whole upper body (torso, head, arms) forward/back around the hips.
	var hip := Vector3.ZERO
	if gparts.has("LegL") and gparts.has("LegR"):
		hip = ((gparts.LegL.rest as Transform3D).origin + (gparts.LegR.rest as Transform3D).origin) / 2
	var r := Basis.from_euler(rot)
	lean_xf = Transform3D(r, hip - r * hip)
	for part in UPPER:
		gpose(part, grot.get(part, Vector3.ZERO))


func part_tip(part: String) -> Vector3:
	# World position of the end of a limb (foot or hand).
	var node := gparts[part].node as Node3D
	var mi := node as MeshInstance3D
	if mi == null or mi.mesh == null:
		for c in node.get_children():
			if c is MeshInstance3D and (c as MeshInstance3D).mesh:
				mi = c
				break
	var box := mi.get_aabb()
	return mi.global_transform * Vector3(box.get_center().x, box.position.y, box.get_center().z)


func walk_pose(phase: float, amount: float) -> void:
	var s := sin(phase) * 0.6 * amount
	gpose("LegL", Vector3(s, 0, 0))
	gpose("LegR", Vector3(-s, 0, 0))
	gpose("ArmL", Vector3(-s * 0.8, 0, -0.1))
	gpose("ArmR", Vector3(s * 0.8, 0, 0.1))
	gpose("Head", Vector3(0, 0, 0.05 * sin(phase * 0.5)))


func giant_show() -> void:
	var size := clampf(height * 2.4, 11.0, 18.0)
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	var attack: String = ["stomp", "kick", "swipe", "smash"][rng.randi() % 4]
	if forced_attack != "":
		attack = forced_attack
	var a := rng.randf() * TAU
	var dir := Vector3(cos(a), 0, sin(a))  # from structure towards where the giant lands
	var reach: float = {"stomp": 0.22, "kick": 0.42, "swipe": 0.45, "smash": 0.5}[attack] * size + radius * 0.4
	var land: Vector3 = centre + dir * (reach + size * 0.9)
	var flat := Vector2(land.x, land.z).limit_length(main.BUILD_R + 1.0)
	land = Vector3(flat.x, 0, flat.y)

	giant = make_giant(size)
	add_child(giant)
	giant.look_at_from_position(land + Vector3(0, 40, 0), centre + Vector3(0, 40, 0), Vector3.UP)
	frame_camera(dir, size * 1.55 + radius, size * 0.42)
	main.flash("Uh oh... GIANT LEVI is coming!")

	# Drop in from the sky.
	await tween_value(40.0, 0.0, 0.9, func(y): giant.global_position = land + Vector3(0, y, 0), Tween.TRANS_QUAD, Tween.EASE_IN)
	main.shake = 0.8
	main.play_sfx(main.thud_snd)
	await wait(0.5)

	# Walk up to the structure.
	var stand: Vector3 = centre + dir * reach
	var from := giant.global_position
	var dist := from.distance_to(stand)
	var steps := maxf(dist / (size * 0.3), 0.6)
	await tween_value(0.0, 1.0, steps, func(k):
		giant.global_position = from.lerp(stand, k)
		walk_pose(k * steps * 6.0, 1.0)
		giant.position.y = absf(sin(k * steps * 6.0)) * size * 0.02, Tween.TRANS_LINEAR)
	walk_pose(0, 0)
	await wait(0.25)

	match attack:
		"stomp":
			await stomp(size)
		"kick":
			await kick(size, -dir)
		"swipe":
			await swipe(size, -dir)
		"smash":
			await smash(size)
	await wait(1.6)

	# Laugh, then leap away.
	main.flash("Ha ha ha!")
	await tween_value(0.0, 1.0, 1.0, func(k):
		gpose("Head", Vector3(-0.35 * sin(k * PI), 0, 0.12 * sin(k * TAU * 3)))
		gpose("ArmL", Vector3(0, 0, -0.6 * sin(k * PI)))
		gpose("ArmR", Vector3(0, 0, 0.6 * sin(k * PI))))
	var top := giant.global_position
	await tween_value(0.0, 1.0, 1.1, func(k): giant.global_position = top + Vector3(0, 45.0 * k * k, 0) + dir * 12.0 * k, Tween.TRANS_LINEAR)
	clear_hitters()
	giant.queue_free()
	giant = null


func stomp(size: float) -> void:
	# Lift a foot way up, lean back... STOMP.
	add_hitter(size * 0.09, part_tip.bind("LegR"))
	await tween_value(0.0, 1.0, 0.8, func(k):
		gpose("LegR", Vector3(-1.5 * k, 0, 0))
		gpose("ArmL", Vector3(0, 0, -0.9 * k))
		gpose("ArmR", Vector3(0, 0, 0.9 * k))
		set_lean(Vector3(-0.15 * k, 0, 0)))
	await wait(0.25)
	await tween_value(1.0, 0.0, 0.16, func(k):
		gpose("LegR", Vector3(-1.5 * k, 0, 0))
		set_lean(Vector3(-0.15 * k, 0, 0)), Tween.TRANS_QUAD, Tween.EASE_IN)
	shatter(centre, Vector3.ZERO, 11.0, radius + size * 0.3)
	main.shake = 1.4


func kick(size: float, toward: Vector3) -> void:
	add_hitter(size * 0.1, part_tip.bind("LegR"))
	await tween_value(0.0, 1.0, 0.55, func(k):
		gpose("LegR", Vector3(0.9 * k, 0, 0))
		gpose("ArmL", Vector3(-0.6 * k, 0, 0))
		gpose("ArmR", Vector3(0.6 * k, 0, 0)))
	await tween_value(0.0, 1.0, 0.22, func(k): gpose("LegR", Vector3(0.9 - 2.4 * k, 0, 0)), Tween.TRANS_QUAD, Tween.EASE_IN)
	shatter(centre + Vector3(0, height * 0.3, 0) - toward * radius * 0.5, toward * 14.0 + Vector3(0, 6, 0), 9.0, radius + size * 0.25)
	await tween_value(0.0, 1.0, 0.5, func(k): gpose("LegR", Vector3(-1.5 * (1.0 - k), 0, 0)))


func swipe(size: float, toward: Vector3) -> void:
	# Arm out to the side, then the whole giant twists so the hand sweeps through.
	add_hitter(size * 0.11, part_tip.bind("ArmR"))
	var yaw0 := giant.rotation.y
	await tween_value(0.0, 1.0, 0.6, func(k):
		gpose("ArmR", Vector3(-0.9 * k, 0, 1.3 * k))
		set_lean(Vector3(0.2 * k, 0, 0))
		giant.rotation.y = yaw0 - 0.9 * k)
	var side := Vector3(-toward.z, 0, toward.x)
	await tween_value(0.0, 1.0, 0.3, func(k): giant.rotation.y = yaw0 - 0.9 + 1.9 * k, Tween.TRANS_QUAD, Tween.EASE_IN)
	shatter(centre + Vector3(0, height * 0.4, 0) + side * radius, -side * 15.0 + Vector3(0, 5, 0), 8.0, radius + size * 0.25)
	await tween_value(0.0, 1.0, 0.6, func(k):
		giant.rotation.y = yaw0 + 1.0 * (1.0 - k)
		gpose("ArmR", Vector3(-0.9 * (1.0 - k), 0, 1.3 * (1.0 - k))))


func smash(size: float) -> void:
	# Both fists up high... and down.
	add_hitter(size * 0.1, part_tip.bind("ArmL"))
	add_hitter(size * 0.1, part_tip.bind("ArmR"))
	await tween_value(0.0, 1.0, 0.7, func(k):
		gpose("ArmL", Vector3(-2.9 * k, 0, 0.25 * k))
		gpose("ArmR", Vector3(-2.9 * k, 0, -0.25 * k))
		set_lean(Vector3(-0.2 * k, 0, 0)))
	await wait(0.3)
	await tween_value(1.0, 0.0, 0.2, func(k):
		gpose("ArmL", Vector3(-2.9 * k - 1.0 * (1.0 - k), 0, 0))
		gpose("ArmR", Vector3(-2.9 * k - 1.0 * (1.0 - k), 0, 0))
		set_lean(Vector3(-0.2 * k + 0.45 * (1.0 - k), 0, 0)), Tween.TRANS_QUAD, Tween.EASE_IN)
	shatter(centre + Vector3(0, height * 0.6, 0), Vector3(0, -4, 0), 12.0, radius + size * 0.3)
	main.shake = 1.5


# ---------------------------------------------------------------- the wrecking ball

func ball_show() -> void:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	var a := rng.randf() * TAU
	var d := Vector3(cos(a), 0, sin(a))  # swing direction (the ball travels along +d)
	var side := Vector3(-d.z, 0, d.x)
	var ball_r := clampf(height * 0.35, 0.9, 2.5)
	var hit_y := clampf(height * 0.45, ball_r * 0.8, height)
	var cable := maxf(height * 1.3, 8.0)
	var pivot := centre + Vector3(0, hit_y + cable, 0)

	# Crane: Blender model if it exists (jib tip at local (9, 14.6, 0)), else a stand-in.
	var tip_local := Vector3(9.0, 14.6, 0)
	var crane: Node3D
	var ball_model: Node3D
	var path := "res://assets/crane/crane.glb"
	if ResourceLoader.exists(path):
		var scene: Node3D = (load(path) as PackedScene).instantiate()
		crane = Node3D.new()
		ball_model = Node3D.new()
		for c in scene.get_children():
			scene.remove_child(c)
			if (c as Node).name.begins_with("Ball"):
				(c as Node3D).position = Vector3.ZERO
				ball_model.add_child(c)
			else:
				crane.add_child(c)
				# Punchier construction yellow than the Blender render.
				for mi in (c as Node).find_children("*", "MeshInstance3D", true, true) + ([c] if c is MeshInstance3D else []):
					var m: Mesh = (mi as MeshInstance3D).mesh
					for i in m.get_surface_count():
						var src := m.surface_get_material(i)
						if src and src.resource_name == "CraneYellow":
							var y := (src as StandardMaterial3D).duplicate() as StandardMaterial3D
							y.albedo_color = Color("f5b800")
							y.roughness = 0.45
							(mi as MeshInstance3D).set_surface_override_material(i, y)
		scene.free()
	else:
		crane = stand_in_crane(tip_local)
		ball_model = MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = 1.0
		sm.height = 2.0
		(ball_model as MeshInstance3D).mesh = sm
		var steel := StandardMaterial3D.new()
		steel.albedo_color = Color("3b3f45")
		steel.metallic = 0.9
		steel.roughness = 0.4
		(ball_model as MeshInstance3D).material_override = steel
	var s := pivot.y / tip_local.y
	crane.scale = Vector3.ONE * s
	var base := pivot - side * tip_local.x * s
	base.y = 0.0
	# Point the jib (+X) at the pivot.
	crane.basis = Basis(side, Vector3.UP, side.cross(Vector3.UP)).scaled(Vector3.ONE * s)
	add_child(crane)
	ball_model.scale = Vector3.ONE * ball_r
	add_child(ball_model)

	var rope := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.06
	cyl.bottom_radius = 0.06
	cyl.height = 1.0
	rope.mesh = cyl
	var rope_mat := StandardMaterial3D.new()
	rope_mat.albedo_color = Color("2a2a2a")
	rope_mat.metallic = 0.6
	rope.material_override = rope_mat
	add_child(rope)

	frame_camera(d, pivot.y * 1.05 + radius * 1.5, pivot.y * 0.35)
	main.flash("Here comes the WRECKING BALL!")

	# Crane drops in from the sky with the ball pulled back.
	var theta := deg_to_rad(-78.0)
	var drop := 60.0
	var place := func(off: float) -> void:
		crane.global_position = base + Vector3(0, off, 0)
		var b := pivot + Vector3(0, off, 0) + (d * sin(theta) - Vector3.UP * cos(theta)) * cable
		ball_model.global_position = b
		var top := pivot + Vector3(0, off, 0)
		var ring := b + Vector3.UP * 1.44 * ball_r  # cable hooks onto the ball's lifting ring
		rope.global_transform = Transform3D(rope_basis(top, ring), (top + ring) / 2)
	await tween_value(drop, 0.0, 1.1, place, Tween.TRANS_QUAD, Tween.EASE_IN)
	main.shake = 0.9
	main.play_sfx(main.thud_snd)
	await wait(0.8)

	# Let go: real pendulum swing, the ball pushes everything it touches.
	var hitter := add_hitter(ball_r, func(): return ball_model.global_position)
	var omega := 0.0
	var g := 30.0
	var smashed := false
	var t := 0.0
	while t < 5.5:
		var dt := get_physics_process_delta_time()
		omega += -(g / cable) * sin(theta) * dt
		omega *= 0.998
		theta += omega * dt
		place.call(0.0)
		if not smashed and theta > deg_to_rad(-12.0):
			smashed = true
			var vel := d * omega * cable
			shatter(ball_model.global_position, vel * 1.1, 12.0, radius + ball_r * 3.0)
			main.shake = 1.3
		t += dt
		await get_tree().physics_frame
	hitter.queue_free()
	hitters.clear()

	# Crane flies off with the ball.
	var th := theta
	await tween_value(0.0, 60.0, 1.4, func(off):
		theta = th
		place.call(off), Tween.TRANS_QUAD, Tween.EASE_IN)
	crane.queue_free()
	ball_model.queue_free()
	rope.queue_free()


func rope_basis(a: Vector3, b: Vector3) -> Basis:
	# Cylinder (Y-up, length 1) stretched from a to b.
	var y := b - a
	var len := y.length()
	var yn := y / len
	var x := yn.cross(Vector3.FORWARD)
	if x.length() < 0.01:
		x = yn.cross(Vector3.RIGHT)
	x = x.normalized()
	var z := x.cross(yn)
	return Basis(x, yn * len, z)


func stand_in_crane(tip: Vector3) -> Node3D:
	var root := Node3D.new()
	var yellow := StandardMaterial3D.new()
	yellow.albedo_color = Color("f2b705")
	for spec in [[Vector3(0, tip.y / 2, 0), Vector3(1.0, tip.y, 1.0)], [Vector3(tip.x / 2 - 1.5, tip.y + 0.4, 0), Vector3(tip.x + 3.0, 0.8, 0.8)]]:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = spec[1]
		mi.mesh = bm
		mi.material_override = yellow
		mi.position = spec[0]
		root.add_child(mi)
	return root
