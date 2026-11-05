import { NB, type Frame } from '../shared/engine'

export interface PhosphorParams { gain: number; pulse: number; making: number; seed: number; compact: number }

const N = 512
const VS = `#version 300 es
precision highp float;
uniform sampler2D uP; uniform float uRow; uniform float uN; uniform vec2 uPx; uniform float uW;
out float vE; out float vU;
void main(){
  int i = gl_InstanceID;
  vec2 a = texelFetch(uP, ivec2(i, int(uRow)), 0).rg;
  vec2 b = texelFetch(uP, ivec2(i+1, int(uRow)), 0).rg;
  vec2 d = (b - a) * uPx; float len = max(length(d), 1e-4);
  vec2 dir = d / len; vec2 nrm = vec2(-dir.y, dir.x);
  int v = gl_VertexID; float side = (v & 1) == 0 ? -1.0 : 1.0; float end = (v >> 1) == 0 ? 0.0 : 1.0;
  vec2 p = mix(a, b, end);
  vec2 off = (nrm * side + dir * (end * 2.0 - 1.0)) * uW / uPx;
  gl_Position = vec4(p + off, 0.0, 1.0);
  vE = side; vU = float(i) / uN;
  // brighter where the beam moves slowly (more dwell), like a real phosphor
  vE = side;
}`
const FS_LINE = `#version 300 es
precision highp float; in float vE; in float vU; uniform float uI; out vec4 o;
void main(){ float c = exp(-vE*vE*2.4); o = vec4(vec3(c * uI), 1.0); }`
const VS_Q = `#version 300 es
void main(){ vec2 p = vec2((gl_VertexID & 1) * 2 - 1, (gl_VertexID >> 1) * 2 - 1); gl_Position = vec4(p, 0.0, 1.0); }`
const FS_DECAY = `#version 300 es
precision highp float; uniform sampler2D uT; uniform vec2 uRes; uniform float uK; out vec4 o;
void main(){ vec4 c = texture(uT, gl_FragCoord.xy / uRes); o = vec4(max(c.rgb * uK - 1.5/255.0, 0.0), 1.0); }`
const FS_OUT = `#version 300 es
precision highp float; uniform sampler2D uT; uniform vec2 uRes; uniform float uPulse; uniform float uMk; uniform float uCompact; uniform float uTime; out vec4 o;
float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
void main(){
  vec2 uv = gl_FragCoord.xy / uRes; vec2 px = 1.0 / uRes;
  float aspect = uRes.x / uRes.y;
  float cab = uPulse * 0.0035;
  float s = texture(uT, uv).r;
  float b = 0.0;
  for (int i = 1; i <= 5; i++) { float r = float(i) * 2.2; vec2 q = px * r;
    b += (texture(uT, uv + vec2(q.x, 0.)).r + texture(uT, uv - vec2(q.x, 0.)).r + texture(uT, uv + vec2(0., q.y)).r + texture(uT, uv - vec2(0., q.y)).r) * (0.30 / float(i)); }
  float I = s + b * 0.55;
  // graticule: fine dots, major crosses
  vec2 g = uv * vec2(aspect * 12.0, 12.0); vec2 gf = abs(fract(g) - 0.5);
  float dots = smoothstep(0.035, 0.0, length(gf - 0.5 + 0.5) - 0.0) * 0.0;
  vec2 cell = fract(g); float dd = length(cell - 0.5); float dot_ = smoothstep(0.055 * (12.0 / (uRes.y / 60.0)) + 0.012, 0.0, dd) * 0.0;
  float gx = smoothstep(1.2 * px.x * 12.0 * aspect, 0.0, abs(cell.x - 0.5) - 0.5 + 0.0) ;
  float line = smoothstep(px.x * 12.0 * aspect * 0.9, 0.0, abs(fract(g.x + 0.0) - 0.0)) + smoothstep(px.y * 12.0 * 0.9, 0.0, abs(fract(g.y) - 0.0));
  float tick = step(abs(uv.y - 0.5), 0.0035) * step(0.35, fract(uv.x * aspect * 60.0 / aspect));
  float grat = (line * 0.045) + tick * 0.12;
  float cross_ = smoothstep(px.x * 1.2, 0.0, abs(uv.x - 0.5)) * 0.07 + smoothstep(px.y * 1.2, 0.0, abs(uv.y - 0.5)) * 0.1;
  vec3 ph = vec3(0.52, 1.0, 0.18);
  vec3 col = ph * (1.0 - exp(-I * 1.6)) * 1.05;
  col += vec3(pow(clamp(I - 0.7, 0.0, 1.0), 1.6)) * 0.9;           // white-hot core
  col += ph * (grat + cross_) * 0.55;
  float sc = 0.94 + 0.06 * sin(gl_FragCoord.y * 3.14159);
  col *= sc;
  vec2 vv = uv - 0.5; col *= 1.0 - dot(vv, vv) * 0.9;
  col += (h(gl_FragCoord.xy + uTime) - 0.5) * 0.012;
  // chromatic edge only on burst
  if (cab > 0.0) { float r = texture(uT, uv + vec2(cab, 0.)).r, bl = texture(uT, uv - vec2(cab, 0.)).r; col.r += r * 0.4 * uPulse; col.b += bl * 0.5 * uPulse; }
  o = vec4(col, 1.0);
}`

export class Phosphor {
  gl: WebGL2RenderingContext
  ok = false
  private pLine!: WebGLProgram; private pDecay!: WebGLProgram; private pOut!: WebGLProgram
  private tex: WebGLTexture[] = []; private fbo: WebGLFramebuffer[] = []; private cur = 0
  private ptex!: WebGLTexture; private data = new Float32Array(N * 2 * 4)
  private w = 0; private h = 0; private time = 0; private seedPhase = 0
  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, preserveDrawingBuffer: true })
    if (!gl) throw new Error('webgl2')
    this.gl = gl
    const mk = (t: number, s: string) => { const sh = gl.createShader(t)!; gl.shaderSource(sh, s); gl.compileShader(sh); if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) ?? 'shader'); return sh }
    const pr = (v: string, f: string) => { const p = gl.createProgram()!; gl.attachShader(p, mk(gl.VERTEX_SHADER, v)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, f)); gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link'); return p }
    this.pLine = pr(VS, FS_LINE); this.pDecay = pr(VS_Q, FS_DECAY); this.pOut = pr(VS_Q, FS_OUT)
    this.ptex = gl.createTexture()!
    gl.bindTexture(gl.TEXTURE_2D, this.ptex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG32F, N, 4, 0, gl.RG, gl.FLOAT, null)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
    this.ok = true
  }
  private alloc() {
    const gl = this.gl
    for (const t of this.tex) gl.deleteTexture(t)
    for (const f of this.fbo) gl.deleteFramebuffer(f)
    this.tex = []; this.fbo = []
    for (let i = 0; i < 2; i++) {
      const t = gl.createTexture()!
      gl.bindTexture(gl.TEXTURE_2D, t)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, this.w, this.h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
      const f = gl.createFramebuffer()!
      gl.bindFramebuffer(gl.FRAMEBUFFER, f); gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0)
      gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT)
      this.tex.push(t); this.fbo.push(f)
    }
  }
  private resize() {
    const d = Math.min(devicePixelRatio || 1, 1.5)
    const w = Math.max(2, Math.round(this.canvas.clientWidth * d)), h = Math.max(2, Math.round(this.canvas.clientHeight * d))
    if (w !== this.w || h !== this.h) { this.w = w; this.h = h; this.canvas.width = w; this.canvas.height = h; this.alloc() }
  }
  private fill(f: Frame, p: PhosphorParams, aspect: number) {
    const d = this.data
    const sqY = aspect > 1 ? 1 : aspect // keep Lissajous square-ish
    const sqX = aspect > 1 ? 1 / aspect : 1
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1)
      const wv = f.wave[i % f.wave.length] ?? 0
      // row 0: waveform across full width
      d[(0 * N + i) * 2] = t * 2 - 1
      d[(0 * N + i) * 2 + 1] = Math.max(-0.95, Math.min(0.95, wv * p.gain * 1.9)) * (p.compact ? 0.9 : 0.5) + (p.compact ? 0 : 0.0)
      // row 1: spectrum, log-ish, drawn as a hanging profile from the bottom
      const bi = Math.min(NB - 1, Math.floor(Math.pow(t, 0.85) * (NB - 1)))
      const sv = Math.min(1, (f.spec[bi] ?? 0) * 1.3)
      d[(1 * N + i) * 2] = t * 2 - 1
      d[(1 * N + i) * 2 + 1] = -0.96 + sv * (p.compact ? 1.5 : 1.15)
      // row 2: lissajous rosette from the waveform against a delayed copy
      const a = f.wave[i % f.wave.length] ?? 0, b = f.wave[(i + 47) % f.wave.length] ?? 0
      const ph = this.seedPhase
      const r = 0.18 + Math.min(0.6, f.level * 1.1 + p.pulse * 0.1)
      const th = t * Math.PI * 6 + ph
      d[(2 * N + i) * 2] = (Math.cos(th * 1.0) * r * (1 + a * 1.8 * p.gain) + b * 0.55) * sqX * (p.compact ? 1 : 0.72)
      d[(2 * N + i) * 2 + 1] = (Math.sin(th * 1.5 + 0.7) * r * (1 + b * 1.8 * p.gain) + a * 0.55) * (aspect > 1 ? 1 : sqY) * (p.compact ? 0.5 : 0.7) - (p.compact ? 0 : 0.14)
      // row 3: per-stem ring (making progress sweeps it)
      const ang = t * Math.PI * 2
      const rr = 0.8 + (p.making > 0 ? Math.sin(ang * 12 + this.time * 3) * 0.015 : 0)
      const prog = p.making > 0 ? Math.min(1, p.making) : 1
      const on = t <= prog ? 1 : 0
      d[(3 * N + i) * 2] = Math.cos(ang - Math.PI / 2) * rr * sqX * on
      d[(3 * N + i) * 2 + 1] = Math.sin(ang - Math.PI / 2) * rr * (aspect > 1 ? 1 : sqY) * on * (p.compact ? 0.5 : 1)
    }
  }
  render(f: Frame, p: PhosphorParams, dt: number) {
    if (!this.ok) return
    const gl = this.gl
    this.resize()
    this.time += dt; this.seedPhase += dt * 0.25 + f.level * dt * 0.8
    const aspect = this.w / this.h
    this.fill(f, p, aspect)
    gl.bindTexture(gl.TEXTURE_2D, this.ptex)
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, N, 4, gl.RG, gl.FLOAT, this.data)
    const src = this.cur, dst = 1 - this.cur
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo[dst]); gl.viewport(0, 0, this.w, this.h)
    gl.disable(gl.BLEND)
    gl.useProgram(this.pDecay)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.tex[src])
    gl.uniform1i(gl.getUniformLocation(this.pDecay, 'uT'), 0); gl.uniform2f(gl.getUniformLocation(this.pDecay, 'uRes'), this.w, this.h)
    gl.uniform1f(gl.getUniformLocation(this.pDecay, 'uK'), Math.pow(0.86, Math.max(0.5, dt * 60)))
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE)
    gl.useProgram(this.pLine)
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.ptex)
    const U = (n: string) => gl.getUniformLocation(this.pLine, n)
    gl.uniform1i(U('uP'), 1); gl.uniform2f(U('uPx'), this.w / 2, this.h / 2)
    const draws: [number, number, number][] = [[0, 2.2, 0.55], [1, 1.8, 0.45], [2, 2.2, 0.5 + f.level * 0.35], [3, 1.6, 0.35]]
    for (const [row, w, I] of draws) {
      if (row === 0 && p.compact === 0) continue // easy: rosette + spectrum + ring, wave is the rosette driver
      gl.uniform1f(U('uRow'), row); gl.uniform1f(U('uN'), N - 1); gl.uniform1f(U('uW'), w * Math.min(devicePixelRatio || 1, 1.5)); gl.uniform1f(U('uI'), I)
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, N - 1)
    }
    gl.disable(gl.BLEND)
    gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, this.w, this.h)
    gl.useProgram(this.pOut)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.tex[dst])
    const O = (n: string) => gl.getUniformLocation(this.pOut, n)
    gl.uniform1i(O('uT'), 0); gl.uniform2f(O('uRes'), this.w, this.h); gl.uniform1f(O('uPulse'), p.pulse); gl.uniform1f(O('uMk'), p.making); gl.uniform1f(O('uCompact'), p.compact); gl.uniform1f(O('uTime'), this.time)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    this.cur = dst
  }
}
