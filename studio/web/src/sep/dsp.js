/**
 * Small, dependency-free DSP kernels for the in-browser RoFormer separators.
 *
 *  - FFT:        iterative radix-2 complex FFT (Float64, cached tables)
 *  - stftFrames: torch.stft(center=True, pad_mode="reflect", hann periodic)
 *                for a STEREO pair, using one complex FFT per frame (L + iR)
 *  - istftFrames: torch.istft(center=True) for a stereo pair, one complex
 *                inverse FFT per frame
 *
 * The numerics mirror PyTorch so the ONNX models (which were exported with the
 * STFT/iSTFT *outside* the graph) see exactly the tensors they were trained on.
 * The STFT/iSTFT layout and reflect-padding conventions were cross-checked
 * against the MIT-licensed elicwhite/bs-roformer-web reference
 * (docs/stft-worker.js) and against torch in tests/parity (see NOTICE.md).
 */

const fftCache = new Map();

export class FFT {
  constructor(n) {
    if (n < 2 || (n & (n - 1)) !== 0) throw new Error('FFT size must be a power of two');
    this.n = n;
    this.rev = new Uint32Array(n);
    const bits = Math.log2(n) | 0;
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0; b < bits; b++) if (i & (1 << b)) r |= 1 << (bits - 1 - b);
      this.rev[i] = r;
    }
    this.cos = new Float64Array(n / 2);
    this.sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      this.cos[i] = Math.cos((2 * Math.PI * i) / n);
      this.sin[i] = -Math.sin((2 * Math.PI * i) / n);
    }
  }

  static get(n) {
    let f = fftCache.get(n);
    if (!f) { f = new FFT(n); fftCache.set(n, f); }
    return f;
  }

  /** In-place forward transform: X[k] = sum x[n] e^{-2*pi*i*k*n/N}. */
  transform(re, im) {
    const n = this.n, rev = this.rev;
    for (let i = 0; i < n; i++) {
      const j = rev[i];
      if (j > i) {
        let t = re[i]; re[i] = re[j]; re[j] = t;
        t = im[i]; im[i] = im[j]; im[j] = t;
      }
    }
    const cs = this.cos, sn = this.sin;
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1;
      const step = n / size;
      for (let start = 0; start < n; start += size) {
        for (let k = 0, tw = 0; k < half; k++, tw += step) {
          const wr = cs[tw], wi = sn[tw];
          const a = start + k, b = a + half;
          const tr = re[b] * wr - im[b] * wi;
          const ti = re[b] * wi + im[b] * wr;
          re[b] = re[a] - tr; im[b] = im[a] - ti;
          re[a] += tr; im[a] += ti;
        }
      }
    }
  }

  /**
   * In-place inverse transform WITHOUT the 1/N scale.
   * Uses ifft(x) = swap(fft(swap(x))): swapping the (re, im) arguments.
   */
  inverseUnscaled(re, im) {
    this.transform(im, re);
  }
}

/** torch.hann_window(n) (periodic=True, the torch.stft default). */
export function hannPeriodic(n) {
  const w = new Float64Array(n);
  for (let i = 0; i < n; i++) w[i] = 0.5 * (1 - Math.cos((2 * Math.PI * i) / n));
  return w;
}

/** Number of STFT frames for `length` samples with center=True. */
export function numFrames(length, hop) {
  return Math.floor(length / hop) + 1;
}

/** torch "reflect" padding index (edge sample not repeated). */
function reflect(i, len) {
  if (i < 0) i = -i;
  if (i >= len) i = 2 * (len - 1) - i;
  // Only needed for inputs shorter than nFft/2; keep it safe.
  if (i < 0 || i >= len) {
    const period = 2 * (len - 1);
    i = ((i % period) + period) % period;
    if (i >= len) i = period - i;
  }
  return i;
}

/**
 * Stereo STFT. For every frame t calls
 *   onFrame(t, reL, imL, reR, imR)
 * with Float64Array(nFft/2+1) spectra (the arrays are reused between calls,
 * copy what you need).
 *
 * Equivalent to torch.stft(x, n_fft=nFft, hop_length=hop, win_length=nFft,
 * window=hann, center=True, pad_mode="reflect", normalized=False).
 */
export function stftFrames(left, right, nFft, hop, onFrame) {
  const len = left.length;
  const T = numFrames(len, hop);
  const F = nFft / 2 + 1;
  const fft = FFT.get(nFft);
  const win = hannPeriodic(nFft);
  const re = new Float64Array(nFft);
  const im = new Float64Array(nFft);
  const reL = new Float64Array(F), imL = new Float64Array(F);
  const reR = new Float64Array(F), imR = new Float64Array(F);
  const half = nFft >> 1;
  for (let t = 0; t < T; t++) {
    const s0 = t * hop - half;
    if (s0 >= 0 && s0 + nFft <= len) {
      for (let i = 0; i < nFft; i++) { re[i] = left[s0 + i] * win[i]; im[i] = right[s0 + i] * win[i]; }
    } else {
      for (let i = 0; i < nFft; i++) {
        const j = reflect(s0 + i, len);
        re[i] = left[j] * win[i]; im[i] = right[j] * win[i];
      }
    }
    fft.transform(re, im);
    // Z = FFT(L + iR); L[k] = (Z[k] + conj Z[N-k]) / 2; R[k] = (Z[k] - conj Z[N-k]) / 2i
    for (let k = 0; k < F; k++) {
      const m = (nFft - k) & (nFft - 1);
      const zr = re[k], zi = im[k], cr = re[m], ci = -im[m];
      reL[k] = 0.5 * (zr + cr); imL[k] = 0.5 * (zi + ci);
      // (Z - conj(Zm)) / (2i) = ((zi - ci) - i (zr - cr)) / 2
      reR[k] = 0.5 * (zi - ci); imR[k] = -0.5 * (zr - cr);
    }
    onFrame(t, reL, imL, reR, imR);
  }
  return { T, F };
}

const envelopeCache = new Map();
function getEnvelope(nFft, hop, T) {
  const key = `${nFft}/${hop}/${T}`;
  let e = envelopeCache.get(key);
  if (e) return e;
  const win = hannPeriodic(nFft);
  const padded = (T - 1) * hop + nFft;
  const env = new Float64Array(padded);
  for (let t = 0; t < T; t++) {
    const o = t * hop;
    for (let i = 0; i < nFft; i++) env[o + i] += win[i] * win[i];
  }
  e = { win, env, padded };
  envelopeCache.set(key, e);
  return e;
}

/**
 * Stereo inverse STFT (torch.istft(center=True, window=hann, length=length)).
 * `getFrame(t, reL, imL, reR, imR)` must fill the four Float64Array(F) spectra
 * for frame t. Writes `length` samples into outL / outR.
 */
export function istftFrames(getFrame, nFft, hop, T, length, outL, outR) {
  const F = nFft / 2 + 1;
  const fft = FFT.get(nFft);
  const { win, env, padded } = getEnvelope(nFft, hop, T);
  const accL = new Float64Array(padded);
  const accR = new Float64Array(padded);
  const re = new Float64Array(nFft);
  const im = new Float64Array(nFft);
  const reL = new Float64Array(F), imL = new Float64Array(F);
  const reR = new Float64Array(F), imR = new Float64Array(F);
  const scale = 1 / nFft;
  for (let t = 0; t < T; t++) {
    getFrame(t, reL, imL, reR, imR);
    // Z = XL + i*XR on the half spectrum, Hermitian-extended for each channel.
    // Imag parts of DC / Nyquist are ignored (they are zero for real signals).
    re[0] = reL[0]; im[0] = reR[0];
    re[F - 1] = reL[F - 1]; im[F - 1] = reR[F - 1];
    for (let k = 1; k < F - 1; k++) {
      const a = reL[k], b = imL[k], c = reR[k], d = imR[k];
      re[k] = a - d; im[k] = b + c;
      const m = nFft - k;
      re[m] = a + d; im[m] = c - b;
    }
    fft.inverseUnscaled(re, im);
    const o = t * hop;
    for (let i = 0; i < nFft; i++) {
      const w = win[i] * scale;
      accL[o + i] += re[i] * w;
      accR[o + i] += im[i] * w;
    }
  }
  const pad = nFft >> 1;
  for (let i = 0; i < length; i++) {
    const e = env[pad + i];
    const inv = e > 1e-11 ? 1 / e : 0;
    outL[i] = accL[pad + i] * inv;
    outR[i] = accR[pad + i] * inv;
  }
}
