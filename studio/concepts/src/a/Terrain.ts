import { NB, type Frame } from '../shared/engine'

export interface TerrainParams {
  focus: number // 0 = full canvas (easy), 1 = top strip (advanced)
  pulse: number // chromatic aberration burst 0..1.5
  mx: number
  my: number
  rough: number
  freq: number
  amp: number
  making: number
}

const ROWS = 72
const VERTS = 256
const VS_LINE = `#version 300 es
precision highp float;
in float aX; in float aB;
uniform sampler2D uH; uniform float uRow; uniform float uHead; uniform float uScroll;
uniform float uFront; uniform float uHorizon; uniform float uAmp; uniform float uDepth; uniform vec2 uPar; uniform float uAspect; uniform float uRough; uniform float uFreq; uniform float uT; uniform float uSpan; uniform float uFill; uniform float uMaking;
out float vZ; out float vH; out float vX;
void main(){
  float zr = uRow + uScroll;
  float z = zr / ${(ROWS - 1).toFixed(1)};
  float rowTex = mod(uHead + uRow, ${ROWS.toFixed(1)});
  vec2 uv = vec2((aX*${(NB - 1).toFixed(1)}+0.5)/${NB.toFixed(1)}, (rowTex+0.5)/${ROWS.toFixed(1)});
  float h = texture(uH, uv).r;
  float x2 = aX*2.0-1.0;
  float shape = mix(0.18, 1.0, pow(max(0.0,1.0-abs(x2)), 1.35));
  // bedrock: slow ridges that morph per vibe
  float bed = (sin(aX*uFreq + z*5.0 + uT*0.15) * 0.5 + 0.5) * 0.06 + (sin(aX*uFreq*2.7 - z*9.0 - uT*0.2)*0.5+0.5) * 0.05 * uRough;
  float hh = (h * shape * uAmp + bed * shape);
  float persp = 1.0 / (1.0 + z * uDepth);
  float sx = x2 * uSpan * persp + uPar.x * z * 0.12;
  float base = uHorizon + (uFront - uHorizon) * persp;
  float y = base + hh * persp + uPar.y * z * 0.05;
  if (aB > 0.5) y = uFill; // bottom of curtain
  gl_Position = vec4(sx, y, 0.0, 1.0);
  vZ = z; vH = h * shape; vX = x2;
}`
const FS_LINE = `#version 300 es
precision highp float;
in float vZ; in float vH; in float vX;
uniform float uFillPass;
out vec4 o;
void main(){
  if (uFillPass > 0.5) { o = vec4(0.0,0.0,0.0,1.0); return; }
  float edge = smoothstep(1.0, 0.55, abs(vX));
  float depth = pow(1.0 - vZ, 0.9);
  float a = (0.16 + 0.84*depth) * (0.35 + 0.65*edge);
  a += vH * 0.55 * depth;
  o = vec4(vec3(0.93,0.95,0.98) * clamp(a,0.0,1.0), 1.0);
}`
const VS_POST = `#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = p*0.5+0.5; gl_Position = vec4(p,0.0,1.0); }`
const FS_POST = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D uScene; uniform float uAber; uniform float uT; uniform vec2 uRes; uniform float uPulse;
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
void main(){
  vec2 c = uv - 0.5;
  float r = length(c * vec2(uRes.x/uRes.y, 1.0));
  vec2 dir = normalize(c + 1e-5) * (0.15 + r);
  float k = uAber * (0.4 + r*1.6);
  float slice = step(0.5, fract(uv.y * 38.0 + uT * 0.6)) * uPulse * 0.004;
  vec3 col;
  col.r = texture(uScene, uv - dir*k + vec2(slice,0.0)).r;
  col.g = texture(uScene, uv).g;
  col.b = texture(uScene, uv + dir*k - vec2(slice,0.0)).b;
  // hairline scanline + grain + vignette
  float sl = 0.965 + 0.035*sin(uv.y*uRes.y*1.5);
  float g = (hash(uv*uRes + fract(uT)*91.7) - 0.5) * 0.045;
  col = col * sl + g * (0.3 + col);
  col *= smoothstep(1.15, 0.35, r);
  o = vec4(max(col, 0.0), 1.0);
}`

export class Terrain {
  gl: WebGL2RenderingContext
  ok = false
  private pl!: WebGLProgram
  private pp!: WebGLProgram
  private vaoLine!: WebGLVertexArrayObject
  private vaoFill!: WebGLVertexArrayObject
  private vaoPost!: WebGLVertexArrayObject
  private tex!: WebGLTexture
  private sceneTex!: WebGLTexture
  private fbo!: WebGLFramebuffer
  private data = new Uint8Array(NB * ROWS)
  private head = 0
  private acc = 0
  private w = 0
  private h = 0
  private u: Record<string, WebGLUniformLocation | null> = {}
  private up: Record<string, WebGLUniformLocation | null> = {}
  private cur = { focus: 0, pulse: 0, mx: 0, my: 0, rough: 0.5, freq: 9, amp: 0.55 }

  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: true })
    this.gl = gl as WebGL2RenderingContext
    if (!gl) return
    this.pl = this.prog(VS_LINE, FS_LINE)
    this.pp = this.prog(VS_POST, FS_POST)
    ;['uH', 'uRow', 'uHead', 'uScroll', 'uFront', 'uHorizon', 'uAmp', 'uDepth', 'uPar', 'uAspect', 'uRough', 'uFreq', 'uT', 'uSpan', 'uFill', 'uFillPass', 'uMaking'].forEach((n) => (this.u[n] = gl.getUniformLocation(this.pl, n)))
    ;['uScene', 'uAber', 'uT', 'uRes', 'uPulse'].forEach((n) => (this.up[n] = gl.getUniformLocation(this.pp, n)))
    // line vertex arrays
    const xs = new Float32Array(VERTS * 2)
    for (let i = 0; i < VERTS; i++) { xs[i * 2] = i / (VERTS - 1); xs[i * 2 + 1] = 0 }
    const vl = gl.createVertexArray()!; gl.bindVertexArray(vl)
    const bl = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, bl)
    const lineData = new Float32Array(VERTS * 2); for (let i = 0; i < VERTS; i++) { lineData[i * 2] = i / (VERTS - 1); lineData[i * 2 + 1] = 0 }
    gl.bufferData(gl.ARRAY_BUFFER, lineData, gl.STATIC_DRAW)
    const aX = gl.getAttribLocation(this.pl, 'aX'), aB = gl.getAttribLocation(this.pl, 'aB')
    gl.enableVertexAttribArray(aX); gl.vertexAttribPointer(aX, 1, gl.FLOAT, false, 8, 0)
    gl.enableVertexAttribArray(aB); gl.vertexAttribPointer(aB, 1, gl.FLOAT, false, 8, 4)
    this.vaoLine = vl
    const vf = gl.createVertexArray()!; gl.bindVertexArray(vf)
    const bf = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, bf)
    const fill = new Float32Array(VERTS * 4); for (let i = 0; i < VERTS; i++) { fill[i * 4] = i / (VERTS - 1); fill[i * 4 + 1] = 0; fill[i * 4 + 2] = i / (VERTS - 1); fill[i * 4 + 3] = 1 }
    gl.bufferData(gl.ARRAY_BUFFER, fill, gl.STATIC_DRAW)
    gl.enableVertexAttribArray(aX); gl.vertexAttribPointer(aX, 1, gl.FLOAT, false, 8, 0)
    gl.enableVertexAttribArray(aB); gl.vertexAttribPointer(aB, 1, gl.FLOAT, false, 8, 4)
    this.vaoFill = vf
    const vp = gl.createVertexArray()!; gl.bindVertexArray(vp)
    const bp = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, bp)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const pa = gl.getAttribLocation(this.pp, 'p'); gl.enableVertexAttribArray(pa); gl.vertexAttribPointer(pa, 2, gl.FLOAT, false, 0, 0)
    this.vaoPost = vp
    gl.bindVertexArray(null)
    // height texture
    this.tex = gl.createTexture()!
    gl.bindTexture(gl.TEXTURE_2D, this.tex)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, NB, ROWS, 0, gl.RED, gl.UNSIGNED_BYTE, this.data)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT)
    this.sceneTex = gl.createTexture()!
    this.fbo = gl.createFramebuffer()!
    this.ok = true
  }
  private prog(vs: string, fs: string) {
    const gl = this.gl
    const mk = (t: number, s: string) => { const sh = gl.createShader(t)!; gl.shaderSource(sh, s); gl.compileShader(sh); if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) console.error(gl.getShaderInfoLog(sh)); return sh }
    const p = gl.createProgram()!
    gl.attachShader(p, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p)
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) console.error(gl.getProgramInfoLog(p))
    return p
  }
  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = Math.floor(this.canvas.clientWidth * dpr), h = Math.floor(this.canvas.clientHeight * dpr)
    if (w === this.w && h === this.h) return
    this.w = w; this.h = h; this.canvas.width = w; this.canvas.height = h
    const gl = this.gl
    gl.bindTexture(gl.TEXTURE_2D, this.sceneTex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo)
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.sceneTex, 0)
  }
  render(f: Frame, p: TerrainParams, dt: number) {
    if (!this.ok) return
    const gl = this.gl
    this.resize()
    // ease parameters
    const k = 1 - Math.pow(0.0015, dt)
    const c = this.cur
    c.focus += (p.focus - c.focus) * (1 - Math.pow(0.02, dt))
    c.mx += (p.mx - c.mx) * k; c.my += (p.my - c.my) * k
    c.rough += (p.rough - c.rough) * k; c.freq += (p.freq - c.freq) * k; c.amp += (p.amp - c.amp) * k
    c.pulse = Math.max(p.pulse, c.pulse * Math.pow(0.02, dt))
    // push history rows at 26 Hz
    this.acc += dt
    const step = 1 / 26
    while (this.acc >= step) {
      this.acc -= step
      this.head = (this.head - 1 + ROWS) % ROWS
      const row = this.head * NB
      for (let i = 0; i < NB; i++) this.data[row + i] = Math.min(255, Math.max(0, Math.round(f.spec[i] * 255)))
      gl.bindTexture(gl.TEXTURE_2D, this.tex)
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, this.head, NB, 1, gl.RED, gl.UNSIGNED_BYTE, this.data.subarray(row, row + NB))
    }
    const scroll = this.acc / step
    const fo = c.focus
    const aspect = this.w / this.h
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo)
    gl.viewport(0, 0, this.w, this.h)
    gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT)
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND)
    gl.useProgram(this.pl)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.tex)
    const u = this.u
    gl.uniform1i(u.uH, 0)
    gl.uniform1f(u.uHead, this.head); gl.uniform1f(u.uScroll, scroll)
    const mobile = aspect < 1
    const front = mobile ? -0.55 + fo * 0.6 : -0.9 + fo * 1.3
    const horizon = mobile ? 0.55 + fo * 0.1 : 0.68 + fo * 0.18
    gl.uniform1f(u.uFront, front); gl.uniform1f(u.uHorizon, horizon)
    gl.uniform1f(u.uAmp, (mobile ? 0.5 : 0.62) * c.amp * (1 - fo * 0.55))
    gl.uniform1f(u.uDepth, 2.4 + fo * 0.6)
    gl.uniform2f(u.uPar, c.mx, c.my)
    gl.uniform1f(u.uAspect, aspect)
    gl.uniform1f(u.uRough, c.rough); gl.uniform1f(u.uFreq, c.freq); gl.uniform1f(u.uT, f.t)
    gl.uniform1f(u.uSpan, mobile ? 1.5 : 1.25)
    gl.uniform1f(u.uMaking, p.making)
    for (let r = ROWS - 1; r >= 0; r--) {
      gl.uniform1f(u.uRow, r)
      gl.uniform1f(u.uFill, -1.2)
      gl.uniform1f(u.uFillPass, 1)
      gl.bindVertexArray(this.vaoFill)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, VERTS * 2)
      gl.uniform1f(u.uFillPass, 0)
      gl.bindVertexArray(this.vaoLine)
      gl.drawArrays(gl.LINE_STRIP, 0, VERTS)
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null)
    gl.viewport(0, 0, this.w, this.h)
    gl.useProgram(this.pp)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.sceneTex)
    gl.uniform1i(this.up.uScene, 0)
    gl.uniform1f(this.up.uAber, 0.0012 + c.pulse * 0.016)
    gl.uniform1f(this.up.uPulse, Math.min(1, c.pulse))
    gl.uniform1f(this.up.uT, f.t)
    gl.uniform2f(this.up.uRes, this.w, this.h)
    gl.bindVertexArray(this.vaoPost)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
    gl.bindVertexArray(null)
  }
}
