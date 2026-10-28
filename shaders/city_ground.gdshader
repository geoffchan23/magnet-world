// The ground of the ruined city: cracked asphalt roads with worn paint, sand
// drifting in from the wasteland, and the dirt lot in the middle where you build
// (with a soft build grid). City blocks themselves are raised pavement slabs.
shader_type spatial;

uniform sampler2D asphalt_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D asphalt_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;

// Must match city.gd.
uniform float lot_half = 15.0;
uniform float road = 5.0;
uniform float block = 20.0;
uniform float city_half = 95.0;
uniform float grid_radius = 12.5;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

// 0 = this coordinate is inside a block (or the lot), 1 = on a road.
float on_road(float a) {
	a = abs(a);
	if (a < lot_half) return 0.0;
	float k = mod(a - lot_half, road + block);
	return k < road ? 1.0 : 0.0;
}

// Distance from a road's centre line, along one axis.
float centre_dist(float a) {
	a = abs(a) - lot_half - road * 0.5;
	float p = road + block;
	return abs(a - p * round(a / p));
}

void fragment() {
	vec2 p = wpos.xz;
	float edge = max(abs(p.x), abs(p.y));
	bool city = edge < city_half;
	bool lot = abs(p.x) < lot_half && abs(p.y) < lot_half;
	float rx = on_road(p.x);
	float rz = on_road(p.y);
	bool road_here = city && !lot && (rx > 0.5 || rz > 0.5);

	float n = texture(noise_tex, p * 0.013).r;
	float n2 = texture(noise_tex, p * 0.071 + vec2(0.3, 0.6)).r;

	vec2 uv = p * 0.33;
	vec3 asphalt = texture(asphalt_tex, uv).rgb;
	asphalt = mix(asphalt, texture(asphalt_tex, uv * 0.21 + vec2(0.4, 0.1)).rgb, 0.4) * vec3(0.95, 0.93, 0.9);
	vec3 dirt = texture(dirt_tex, p * 0.28).rgb;
	dirt = mix(dirt, texture(dirt_tex, p * 0.061 + vec2(0.7, 0.2)).rgb, 0.45);
	vec3 sand = dirt * vec3(1.35, 1.18, 0.95);

	vec3 col;
	float rough = 0.9;
	float nmix;  // 0 = asphalt normals, 1 = dirt normals
	if (road_here) {
		col = asphalt;
		nmix = 0.0;
		// Faded paint: dashed yellow centre lines, crossings stay bare.
		float paint = 0.0;
		if (rz > 0.5 && rx < 0.5) {
			float d = centre_dist(p.y);
			paint = (1.0 - smoothstep(0.06, 0.09, d)) * step(0.45, fract(p.x / 2.4));
			// Zebra crossing at each end of the block.
			float into = abs(p.x) < lot_half ? 99.0 : mod(abs(p.x) - lot_half, road + block) - road;
			float far_end = block - into;
			float zc = min(into, far_end);
			if (zc > 0.3 && zc < 1.5 && d < road * 0.42) paint = max(paint, step(0.5, fract(p.y * 1.4)));
		} else if (rx > 0.5 && rz < 0.5) {
			float d = centre_dist(p.x);
			paint = (1.0 - smoothstep(0.06, 0.09, d)) * step(0.45, fract(p.y / 2.4));
			float into = abs(p.y) < lot_half ? 99.0 : mod(abs(p.y) - lot_half, road + block) - road;
			float far_end = block - into;
			float zc = min(into, far_end);
			if (zc > 0.3 && zc < 1.5 && d < road * 0.42) paint = max(paint, step(0.5, fract(p.x * 1.4)));
		}
		vec3 paint_col = (rx > 0.5 && rz > 0.5) ? vec3(0.8) : vec3(0.85, 0.66, 0.2);
		paint *= smoothstep(0.25, 0.6, n2);  // worn away in patches
		col = mix(col, paint_col, paint * 0.75);
		rough = mix(0.88, 0.75, paint);
		// Sand drifted across the road, heavier towards the city edge.
		float drift = smoothstep(0.55, 0.75, n + edge / city_half * 0.25);
		col = mix(col, sand, drift);
		nmix = drift;
	} else {
		col = city ? dirt * vec3(1.08, 1.0, 0.92) : mix(sand, dirt, smoothstep(0.3, 0.7, n));
		nmix = 1.0;
		if (lot) {
			vec2 f = fract(p);
			vec2 d = min(f, 1.0 - f);
			vec2 w = fwidth(p) * 1.2;
			float line = 1.0 - min(smoothstep(0.0, w.x + 0.012, d.x), smoothstep(0.0, w.y + 0.012, d.y));
			float inside = 1.0 - smoothstep(grid_radius - 0.8, grid_radius, length(p));
			col = mix(col, col * 1.6 + 0.06, line * inside * 0.55);
		}
	}

	vec3 wn = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
	vec3 na = texture(asphalt_nrm, uv).rgb * 2.0 - 1.0;
	vec3 nd = texture(dirt_nrm, p * 0.28).rgb * 2.0 - 1.0;
	vec3 nm = mix(na, nd, nmix);
	wn = normalize(wn + vec3(nm.x, 0.0, -nm.y) * 0.6);
	NORMAL = (VIEW_MATRIX * vec4(wn, 0.0)).xyz;

	ALBEDO = col;
	ROUGHNESS = rough;
	SPECULAR = 0.3;
}
