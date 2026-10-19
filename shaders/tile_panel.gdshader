// Translucent moulded plastic window of a magnet tile.
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_never;

uniform vec4 tint : source_color = vec4(0.2, 0.6, 1.0, 1.0);
uniform float clarity = 0.42;   // alpha when looking straight through
uniform float ridge_freq = 70.0;
uniform float ridge_amount = 0.06;

varying vec3 lpos;

void vertex() {
	lpos = VERTEX;
}

void fragment() {
	// Fine moulded ribbing, like the real tiles have.
	float r = cos((lpos.x + lpos.z) * ridge_freq);
	vec3 local_bump = normalize(vec3(1.0, 0.0, 1.0)) * r * ridge_amount;
	NORMAL = normalize(NORMAL + (VIEW_MATRIX * (MODEL_MATRIX * vec4(local_bump, 0.0))).xyz);

	float facing = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	float fres = pow(1.0 - facing, 3.0);
	ALBEDO = tint.rgb * 0.85;
	ALPHA = mix(clarity, 0.92, fres);
	ROUGHNESS = 0.05;
	SPECULAR = 0.75;
	BACKLIGHT = tint.rgb * 0.75;   // sunlight glowing through the plastic
	EMISSION = tint.rgb * 0.05;
}
