"""
GLSL fragment shaders — one per visual mode.

Every shader receives the same uniforms:
  u_resolution  vec2   window size in pixels
  u_time        float  seconds since start
  u_beat        float  beat phase 0.0 (just fired) → 1.0 (next imminent)
  u_bpm         float  current BPM
  u_volume      float  overall loudness 0–1
  u_bass        float  40–200 Hz energy 0–1
  u_mid         float  200–2000 Hz energy 0–1
  u_high        float  2000–8000 Hz energy 0–1
"""

# Shared vertex shader — just passes a full-screen quad through.
VERT = """
#version 330
in vec2 in_vert;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1. RIPPLE  —  water-surface interference pattern
# ─────────────────────────────────────────────────────────────────────────────
RIPPLE = """
#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_beat;
uniform float u_bpm;
uniform float u_volume;
uniform float u_bass;

out vec4 fragColor;

void main() {
    vec2 uv  = (gl_FragCoord.xy - u_resolution * 0.5) / min(u_resolution.x, u_resolution.y);
    float spd = u_bpm / 60.0;
    float t   = u_time * spd;

    // Three interference sources
    float w  = sin(length(uv) * 28.0 - t * 3.2) * 0.50;
    w += sin(length(uv - vec2( 0.30,  0.20)) * 22.0 - t * 2.5) * 0.28;
    w += sin(length(uv + vec2( 0.25, -0.30)) * 25.0 - t * 2.8) * 0.28;

    // Beat splash — bass drives the amplitude
    float splash = exp(-u_beat * 4.5) * (0.3 + u_bass * 0.8);
    w += sin(length(uv) * 14.0) * splash * 2.2;

    float v = w * 0.5 + 0.5;

    vec3 deep  = vec3(0.00, 0.04, 0.28);
    vec3 mid   = vec3(0.00, 0.42, 0.82);
    vec3 crest = vec3(0.75, 0.95, 1.00);

    vec3 col = mix(deep, mid,   smoothstep(0.20, 0.52, v));
    col      = mix(col,  crest, smoothstep(0.60, 0.90, v));
    col     *= 0.35 + u_volume * 1.3;
    col     += splash * 0.35 * vec3(0.5, 0.85, 1.0);

    fragColor = vec4(col, 1.0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 2. PLASMA  —  overlapping sine-wave colour field
# ─────────────────────────────────────────────────────────────────────────────
PLASMA = """
#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_beat;
uniform float u_bpm;
uniform float u_volume;
uniform float u_mid;
uniform float u_high;

out vec4 fragColor;

#define PI 3.14159265

void main() {
    vec2  uv = gl_FragCoord.xy / u_resolution;
    float t  = u_time * u_bpm / 120.0;

    float v = sin(uv.x *  8.0 + t)
            + sin(uv.y *  8.0 + t * 0.90)
            + sin((uv.x + uv.y) * 6.0 + t * 0.80)
            + sin(length(uv - 0.5) * 22.0 + t);

    v += u_mid  * sin(uv.x * 22.0 + t * 2.0) * 0.55;
    v += u_high * sin(uv.y * 34.0 - t * 3.2) * 0.35;
    v += exp(-u_beat * 5.0) * 2.2;          // beat flash

    vec3 col = 0.5 + 0.5 * cos(v * PI * 0.5 + vec3(0.0, 2.094, 4.189));
    col *= 0.45 + u_volume * 0.85;

    fragColor = vec4(col, 1.0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 3. TUNNEL  —  infinite corridor with code-rain aesthetic
# ─────────────────────────────────────────────────────────────────────────────
TUNNEL = """
#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_beat;
uniform float u_bpm;
uniform float u_volume;
uniform float u_bass;

out vec4 fragColor;

float hash2(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
    vec2  uv = (gl_FragCoord.xy - u_resolution * 0.5) / u_resolution.y;
    float r  = length(uv) + 1e-5;
    float a  = atan(uv.y, uv.x) / (2.0 * 3.14159);

    // Forward speed pulses on beat
    float z   = u_time * u_bpm / 120.0 * 0.45
              + exp(-u_beat * 3.5) * 0.3;
    float dep = 0.28 / r;

    // Tile the tunnel into a grid of "cells"
    vec2  tile = vec2(fract(a * 10.0), fract(dep - z));
    float grid = step(0.88, max(tile.x, tile.y));

    // Each cell gets a random "glyph brightness" that flickers
    float ch = hash2(floor(vec2(a * 10.0, dep - z)));
    float flicker = 0.5 + 0.5 * sin(ch * 60.0 + u_time * (2.0 + ch * 4.0));

    // Green-on-black matrix palette
    vec3 col = mix(
        vec3(0.0,  flicker * (1.0 - grid) * 0.85, 0.0),   // glyph body
        vec3(0.6,  1.0, 0.6) * grid,                        // cell border
        grid * 0.4
    );
    col *= clamp(dep * r * 2.8, 0.0, 1.0);                  // depth fade
    col += exp(-u_beat * 6.0) * u_bass * vec3(0.0, 0.4, 0.15);
    col *= 0.3 + u_volume * 1.3;

    fragColor = vec4(col, 1.0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 4. FIRE  —  fbm noise procedural fire
# ─────────────────────────────────────────────────────────────────────────────
FIRE = """
#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_beat;
uniform float u_bpm;
uniform float u_volume;
uniform float u_bass;

out vec4 fragColor;

float hash(vec2 p) {
    p  = fract(p * vec2(234.34, 435.35));
    p += dot(p, p + 34.23);
    return fract(p.x * p.y);
}

float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1,0)), f.x),
               mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0, a = 0.52;
    for (int i = 0; i < 6; i++) {
        v += a * noise(p);
        p  = p * 2.07 + vec2(1.7, 9.2);
        a *= 0.50;
    }
    return v;
}

void main() {
    vec2  uv  = gl_FragCoord.xy / u_resolution;
    uv.y      = 1.0 - uv.y;
    float spd = u_bpm / 120.0;
    float t   = u_time * spd;
    float surge = exp(-u_beat * 2.2) * (0.25 + u_bass * 0.45);

    vec2  p = uv * vec2(2.2, 3.2);
    p.x    += fbm(p * 1.6 + vec2(0.0, t * 0.9)) * 0.42;
    float f = fbm(p + vec2(0.0, t)) - uv.y * (1.25 - surge);
    f       = clamp(f * (1.6 + u_volume * 0.8), 0.0, 1.0);

    vec3 col = mix(vec3(0.0),          vec3(1.6, 0.45, 0.0), smoothstep(0.00, 0.30, f));
    col      = mix(col, vec3(1.0, 0.90, 0.15),               smoothstep(0.30, 0.70, f));
    col      = mix(col, vec3(1.0, 1.00, 0.95),               smoothstep(0.70, 1.00, f));

    fragColor = vec4(col, 1.0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 5. GALAXY  —  nebula clouds + stars that burst on beat
# ─────────────────────────────────────────────────────────────────────────────
GALAXY = """
#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_beat;
uniform float u_bpm;
uniform float u_volume;
uniform float u_bass;
uniform float u_mid;

out vec4 fragColor;

float hash1(float n)   { return fract(sin(n) * 43758.5453); }
float hash2(vec2  p)   { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5); }

float star(vec2 uv, vec2 pos, float sz) {
    return smoothstep(sz, 0.0, length(uv - pos));
}

void main() {
    vec2  uv   = (gl_FragCoord.xy - u_resolution * 0.5) / u_resolution.y;
    float t    = u_time * 0.18;
    float beat = exp(-u_beat * 3.2) * (0.4 + u_bass * 0.8);

    // Nebula layers
    vec3 col = vec3(0.0);
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        vec2 p   = uv * (1.0 + fi * 0.55)
                 + vec2(cos(t * (0.11 + fi * 0.03)), sin(t * (0.08 + fi * 0.02)));
        float n  = hash2(floor(p * 2.8));
        float cl = exp(-length(fract(p * 2.8) - 0.5) * 7.0) * n * (0.5 + u_mid * 0.5);
        col     += cl * 0.14 * vec3(hash1(fi*1.1+0.5), hash1(fi*2.3+0.3)*0.45, hash1(fi*0.7+0.8));
    }

    // Stars — drift slowly, burst outward on beat
    for (int i = 0; i < 70; i++) {
        float fi  = float(i);
        vec2  dir = vec2(cos(hash1(fi)*6.28), sin(hash1(fi+0.5)*6.28));
        vec2  pos = dir * hash1(fi+1.0) * 0.85 + dir * beat * 0.28;
        float br  = hash1(fi+2.0) * (0.5 + u_volume * 0.6) * (1.0 + beat * 2.5);
        float sz  = 0.004 + hash1(fi+3.0) * 0.009;
        col      += star(uv, pos, sz) * br
                  * mix(vec3(0.8,0.9,1.0), vec3(1.0,0.75,0.4), hash1(fi+4.0));
    }

    col *= 0.28 + u_volume * 1.6;
    col += beat * 0.18 * vec3(0.28, 0.18, 0.80);

    fragColor = vec4(col, 1.0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# 6. SPECTRUM  —  circular audio spectrum rings (used under the dancer)
# ─────────────────────────────────────────────────────────────────────────────
SPECTRUM = """
#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_beat;
uniform float u_bpm;
uniform float u_volume;
uniform float u_bass;
uniform float u_mid;
uniform float u_high;

out vec4 fragColor;

void main() {
    vec2  uv   = gl_FragCoord.xy / u_resolution;
    vec2  c    = uv - 0.5;
    float r    = length(c) * 2.0;
    float a    = atan(c.y, c.x);
    float t    = u_time * u_bpm / 120.0 * 0.5;
    float beat = exp(-u_beat * 4.0);

    // Rotating spectrum: each band modulates a ring radius
    float bassR = 0.28 + u_bass * 0.12 + beat * u_bass * 0.08;
    float midR  = 0.52 + u_mid  * 0.10 + beat * u_mid  * 0.06;
    float highR = 0.74 + u_high * 0.08 + beat * u_high * 0.04;

    float bw = 0.018 + u_bass * 0.012;
    float mw = 0.014 + u_mid  * 0.010;
    float hw = 0.010 + u_high * 0.008;

    vec3 col = vec3(0.04, 0.0, 0.10);  // deep-space background

    // Bass ring (red-orange, thick)
    float bassRing = exp(-pow((r - bassR) / bw, 2.0));
    col += bassRing * (0.5 + u_bass * 0.8)
         * mix(vec3(1.0, 0.2, 0.0), vec3(1.0, 0.6, 0.0),
               0.5 + 0.5 * sin(a * 3.0 + t));

    // Mid ring (cyan, medium)
    float midRing = exp(-pow((r - midR) / mw, 2.0));
    col += midRing * (0.4 + u_mid * 0.8)
         * mix(vec3(0.0, 0.8, 1.0), vec3(0.2, 1.0, 0.6),
               0.5 + 0.5 * sin(a * 5.0 - t * 1.3));

    // High ring (white-purple, thin)
    float highRing = exp(-pow((r - highR) / hw, 2.0));
    col += highRing * (0.3 + u_high * 0.9)
         * mix(vec3(0.8, 0.4, 1.0), vec3(1.0, 1.0, 1.0),
               0.5 + 0.5 * sin(a * 8.0 + t * 2.0));

    // Beat flash: bright central pulse
    col += beat * u_bass * 0.5 * vec3(0.4, 0.2, 1.0) * (1.0 - r);

    col *= 0.35 + u_volume * 1.4;

    fragColor = vec4(col, 1.0);
}
"""

# Map mode name → fragment source
FRAG_BY_MODE = {
    "ripple":    RIPPLE,
    "plasma":    PLASMA,
    "matrix":    TUNNEL,
    "fire":      FIRE,
    "particles": GALAXY,
    "dancer":    SPECTRUM,
}

MODE_NAMES = list(FRAG_BY_MODE.keys())
