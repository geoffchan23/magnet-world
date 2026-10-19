// Grass on top of the floating island, with a soft build grid on the flat part.
shader_type spatial;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 grass_tint : source_color = vec3(0.62, 0.95, 0.42);
uniform float scale = 0.45;
uniform float grid_radius = 6.6;
uniform float grid_strength = 1.0;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv = wpos.xz * scale;
	vec3 g = texture(albedo_tex, uv).rgb;
	g = mix(g, texture(albedo_tex, uv * 0.23 + vec2(0.31, 0.7)).rgb, 0.45);  // hide tiling
	g *= COLOR.rgb * grass_tint;

	vec2 f = fract(wpos.xz);
	vec2 d = min(f, 1.0 - f);
	vec2 w = fwidth(wpos.xz) * 1.2;
	float line = 1.0 - min(smoothstep(0.0, w.x + 0.012, d.x), smoothstep(0.0, w.y + 0.012, d.y));
	float inside = 1.0 - smoothstep(grid_radius - 0.8, grid_radius, length(wpos.xz));
	g = mix(g, g * 1.5 + 0.05, line * inside * 0.5 * grid_strength);

	vec3 wn = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
	vec3 nm = texture(normal_tex, uv).rgb * 2.0 - 1.0;
	wn = normalize(wn + vec3(nm.x, 0.0, -nm.y) * 0.5);
	NORMAL = (VIEW_MATRIX * vec4(wn, 0.0)).xyz;

	ALBEDO = g;
	ROUGHNESS = 0.92;
	SPECULAR = 0.25;
}
