// Grass tufts: dark at the root, sunlit at the tip, swaying in the wind.
shader_type spatial;
render_mode cull_disabled;

uniform vec3 root_color : source_color = vec3(0.16, 0.32, 0.08);
uniform vec3 tip_color : source_color = vec3(0.55, 0.85, 0.3);

varying float tip;

void vertex() {
	tip = UV.y;
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float sway = sin(TIME * 1.8 + wp.x * 0.7 + wp.z * 0.5) * 0.05 + sin(TIME * 3.1 + wp.x * 2.0) * 0.015;
	VERTEX.x += sway * tip * tip;
	VERTEX.z += sway * 0.6 * tip * tip;
}

void fragment() {
	ALBEDO = mix(root_color, tip_color * COLOR.rgb, tip);
	ROUGHNESS = 0.8;
	BACKLIGHT = tip_color * 0.4 * tip;
}
