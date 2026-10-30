shader_type spatial;
// The Reality Stone's pool: thick red Aether goo that swirls and glows.
render_mode cull_disabled;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p), f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void fragment() {
	vec2 p = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xz * 0.6;
	float t = TIME * 0.25;
	float n = noise(p + vec2(t, -t * 0.7)) * 0.6 + noise(p * 2.3 - vec2(t * 1.3, t)) * 0.4;
	float veins = smoothstep(0.45, 0.5, n) - smoothstep(0.5, 0.58, n);
	vec3 deep = vec3(0.22, 0.0, 0.03);
	vec3 hot = vec3(1.0, 0.18, 0.22);
	ALBEDO = mix(deep, hot, n * n * 0.5);
	EMISSION = hot * (0.12 + veins * 0.9 + n * 0.1);
	ROUGHNESS = 0.15;
	SPECULAR = 0.8;
}
