extends RefCounted
## Every vehicle you can summon from the Items menu, and what makes each special.
##
## "car" rides use vehicle.gd (real wheels and suspension); "fly" rides use
## flyer.gd (arcade flying). F does the ride's special move, G honks.

const RIDES := {
	"buggy": {"name": "Scavenger Buggy", "type": "car", "engine": 210.0, "top": 13.0, "mass": 120.0, "special": "boost"},
	"fire_truck": {"name": "Fire Truck", "type": "car", "engine": 330.0, "top": 10.0, "mass": 240.0, "special": "hose"},
	"police_car": {"name": "Police Car", "type": "car", "engine": 260.0, "top": 16.0, "mass": 150.0, "special": "siren"},
	"garbage_truck": {"name": "Garbage Truck", "type": "car", "engine": 340.0, "top": 9.0, "mass": 260.0, "special": "scoop"},
	"race_car": {"name": "Race Car", "type": "car", "engine": 300.0, "top": 22.0, "mass": 110.0, "special": "boost", "grip": 4.2},
	"monster_truck": {"name": "Monster Truck", "type": "car", "engine": 330.0, "top": 14.0, "mass": 220.0, "special": "jump", "travel": 0.32},
	"ice_cream_truck": {"name": "Ice Cream Truck", "type": "car", "engine": 260.0, "top": 10.0, "mass": 200.0, "special": "jingle"},
	"sleigh": {"name": "Santa's Sleigh", "type": "fly", "style": "hover", "top": 11.0, "special": "presents"},
	"plane": {"name": "Plane", "type": "fly", "style": "plane", "top": 18.0, "special": "loop"},
	"helicopter": {"name": "Helicopter", "type": "fly", "style": "hover", "top": 10.0, "special": "spotlight"},
	"rocket": {"name": "Rocket Ship", "type": "fly", "style": "rocket", "top": 26.0, "special": "boost"},
	"hoverboard": {"name": "Hoverboard", "type": "fly", "style": "hover", "top": 9.0, "special": "boost", "low": true},
	"jetpack": {"name": "Jetpack", "type": "fly", "style": "hover", "top": 9.0, "special": "boost", "low": true},
}

const SPECIAL_TEXT := {
	"hose": "F spray water", "siren": "F siren", "scoop": "F scoop up junk", "boost": "F turbo boost",
	"jump": "F big jump", "jingle": "F play the ice cream song", "presents": "F drop presents",
	"loop": "F do a loop", "spotlight": "F spotlight",
}


static func model_path(kind: String) -> String:
	return "res://assets/vehicles/%s.glb" % kind


static func available(kind: String) -> bool:
	return ResourceLoader.exists(model_path(kind))


static func seat_driver(ride: Node3D, seat: Transform3D, character: String, standing := false) -> Node3D:
	# A copy of your explorer, sitting in the seat (or standing, on a hoverboard).
	var d: Node3D = (load("res://assets/characters/%s.glb" % character) as PackedScene).instantiate()
	ride.add_child(d)
	d.transform = seat * Transform3D(Basis().scaled(Vector3.ONE * 0.55), Vector3.ZERO)
	if standing:
		return d
	for part in ["LegL", "LegR"]:
		var n := d.find_child(part, true, false) as Node3D
		if n:
			n.rotate_object_local(Vector3.RIGHT, -1.45)
	for part in ["ArmL", "ArmR"]:
		var n := d.find_child(part, true, false) as Node3D
		if n:
			n.rotate_object_local(Vector3.RIGHT, -1.2)
	return d


static func synth(kind: String) -> AudioStreamWAV:
	# Little made-up sounds, so there are no audio files to ship.
	var rate := 22050
	var secs := {"engine": 0.25, "rotor": 0.25, "jet": 0.25, "siren": 1.2, "horn": 0.45, "jingle": 3.2, "water": 0.5}.get(kind, 0.5) as float
	var n := int(rate * secs)
	var data := PackedByteArray()
	data.resize(n * 2)
	var notes := [0, 4, 7, 12, 7, 4, 0, 4, 7, 4, 0, -5, 0, 4, 7, 12]  # a twinkly tune
	var phase := 0.0
	for i in n:
		var t := float(i) / rate
		var s := 0.0
		match kind:
			"engine":
				s = (sin(TAU * 64.0 * t) * 0.6 + sin(TAU * 128.0 * t) * 0.25 + (randf() - 0.5) * 0.15) * (0.6 + 0.4 * sin(TAU * 24.0 * t))
			"rotor":
				s = (randf() - 0.5) * 0.7 * pow(absf(sin(TAU * 12.0 * t)), 6.0) + sin(TAU * 55.0 * t) * 0.2
			"jet":
				s = (randf() - 0.5) * 0.6 + sin(TAU * 90.0 * t) * 0.1
			"siren":
				var f := 700.0 if fmod(t, 1.2) < 0.6 else 950.0
				phase += TAU * f / rate
				s = sin(phase) * 0.5 + sin(phase * 2.0) * 0.12
			"horn":
				s = (sin(TAU * 330.0 * t) + sin(TAU * 415.0 * t)) * 0.35 * minf(1.0, (secs - t) * 20.0)
			"jingle":
				var k := int(t / 0.2) % notes.size()
				var f := 523.25 * pow(2.0, notes[k] / 12.0)
				var env := exp(-fmod(t, 0.2) * 12.0)
				s = (sin(TAU * f * t) + 0.3 * sin(TAU * f * 2.0 * t)) * 0.4 * env
			"water":
				s = (randf() - 0.5) * 0.5
		data.encode_s16(i * 2, int(clampf(s * 0.6, -1.0, 1.0) * 32767))
	var w := AudioStreamWAV.new()
	w.format = AudioStreamWAV.FORMAT_16_BITS
	w.mix_rate = rate
	w.data = data
	if kind in ["engine", "rotor", "jet", "siren", "water"]:
		w.loop_mode = AudioStreamWAV.LOOP_FORWARD
		w.loop_end = n
	return w
