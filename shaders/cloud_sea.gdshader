// Soft drifting cloud layer far below the islands.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled;

uniform sampler2D noise_tex : repeat_enable, filter_linear_mipmap;
uniform float fade_radius = 220.0;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv = wpos.xz * 0.006;
	float t = TIME * 0.004;
	float n = texture(noise_tex, uv + vec2(t, t * 0.6)).r * 0.6 + texture(noise_tex, uv * 2.3 - vec2(t * 1.7, 0.0)).r * 0.4;
	float cloud = smoothstep(0.38, 0.72, n);
	float fade = 1.0 - smoothstep(fade_radius * 0.5, fade_radius, length(wpos.xz - CAMERA_POSITION_WORLD.xz));
	ALBEDO = mix(vec3(0.72, 0.8, 0.92), vec3(1.0), cloud);
	ALPHA = (0.35 + 0.6 * cloud) * fade;
}
