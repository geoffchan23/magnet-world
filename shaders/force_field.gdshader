shader_type spatial;
// A see-through energy dome around a stone site: bright at the edges, with
// hexagon shimmer drifting over it. Only vehicles bump into it.
render_mode unshaded, cull_disabled, blend_add, depth_draw_never, shadows_disabled;

uniform vec3 tint : source_color = vec3(0.7, 0.4, 1.0);

void fragment() {
	float rim = pow(1.0 - abs(dot(NORMAL, VIEW)), 2.5);
	vec2 uv = UV * vec2(48.0, 24.0);
	vec2 r = vec2(1.0, 1.732);
	vec2 a = mod(uv, r) - r * 0.5;
	vec2 b = mod(uv - r * 0.5, r) - r * 0.5;
	vec2 g = dot(a, a) < dot(b, b) ? a : b;
	float hex = smoothstep(0.38, 0.46, length(g));
	float wave = 0.5 + 0.5 * sin(UV.y * 40.0 - TIME * 2.0);
	float k = rim * 0.3 + hex * 0.05 * wave * rim;
	ALBEDO = tint * k;
}
