/**
 * RoformerEngine: owns one onnxruntime session at a time and runs a whole
 * track through it. Environment-agnostic: the Web Worker, the Node tests and
 * (in principle) the main thread all drive this same class.
 *
 *   const engine = new RoformerEngine({ ort, getModelFiles, log });
 *   await engine.load('mini', { device: 'auto', onProgress });
 *   const { stems } = await engine.separate(left, right, { onProgress });
 *
 * `getModelFiles(model, onProgress)` -> Promise<{ [file.name]: Uint8Array }>
 */

import { MODELS } from './models.js';
import { ADAPTERS } from './adapters.js';
import { separateTrack, CancelledError } from './separator.js';

export class BadGpuOutputError extends Error {
  constructor(msg) { super(msg); this.name = 'BadGpuOutputError'; }
}

function maxAbs(a) {
  let m = 0;
  for (let i = 0; i < a.length; i++) { const v = Math.abs(a[i]); if (!(v <= m)) m = v; }
  return m;
}

export class RoformerEngine {
  constructor({ ort, getModelFiles, log = () => {}, webgpuAvailable, cpuProvider = 'wasm' }) {
    this.cpuProvider = cpuProvider; // 'wasm' in browsers; tests on onnxruntime-node pass 'cpu'
    this.ort = ort;
    this.getModelFiles = getModelFiles;
    this.log = log;
    this.webgpuAvailable = webgpuAvailable ?? (typeof navigator !== 'undefined' && !!navigator.gpu);
    this.session = null;
    this.model = null;
    this.backend = null; // 'webgpu' | 'wasm'
    this.files = null;   // kept so we can rebuild the session on a different EP
    this.cancelled = false;
  }

  async #createSession(model, files, backend) {
    const modelFile = model.files.find((f) => f.role === 'model');
    const dataFiles = model.files.filter((f) => f.role === 'data');
    const options = {
      executionProviders: backend === 'webgpu' ? [{ name: 'webgpu', ...(model.webgpuOptions || {}) }] : [this.cpuProvider],
      graphOptimizationLevel: 'all',
      logSeverityLevel: 3, // silence benign graph-cleanup warnings
    };
    if (dataFiles.length) {
      options.externalData = dataFiles.map((f) => ({ path: f.name, data: files[f.name] }));
    }
    return this.ort.InferenceSession.create(files[modelFile.name], options);
  }

  /** Download (or read from cache) the model files and create an inference session. */
  async load(modelId, { device = 'auto', onProgress } = {}) {
    const model = MODELS[modelId];
    if (!model) throw new Error(`Unknown model "${modelId}"`);
    await this.unload();
    onProgress?.({ phase: 'download', modelId, loaded: 0, total: model.sizeBytes });
    const files = await this.getModelFiles(model, (p) => onProgress?.({ phase: 'download', modelId, ...p }));
    onProgress?.({ phase: 'init', modelId });

    const wantGpu = device === 'webgpu' || (device === 'auto' && this.webgpuAvailable);
    let backend = wantGpu ? 'webgpu' : 'wasm';
    let session = null;
    let gpuError = null;
    if (backend === 'webgpu') {
      try {
        session = await this.#createSession(model, files, 'webgpu');
      } catch (e) {
        gpuError = e;
        this.log('WebGPU session failed, falling back to WASM:', e);
        backend = 'wasm';
      }
    }
    if (!session) session = await this.#createSession(model, files, 'wasm');

    this.model = model;
    this.session = session;
    this.backend = backend;
    this.files = files;
    onProgress?.({ phase: 'ready', modelId, backend, gpuError: gpuError ? String(gpuError.message || gpuError) : null });
    return { backend, gpuError: gpuError ? String(gpuError.message || gpuError) : null };
  }

  async unload() {
    try { await this.session?.release?.(); } catch { /* ignore */ }
    this.session = null;
    this.model = null;
    this.files = null;
    this.backend = null;
  }

  cancel() { this.cancelled = true; }

  async #switchToWasm(reason, onProgress) {
    this.log('Falling back to WASM:', reason);
    try { await this.session?.release?.(); } catch { /* ignore */ }
    this.session = await this.#createSession(this.model, this.files, 'wasm');
    this.backend = 'wasm';
    onProgress?.({ phase: 'fallback', backend: 'wasm', reason: String(reason) });
  }

  /**
   * @param {Float32Array} left  44.1 kHz samples
   * @param {Float32Array} right
   * @param {{ createSink?: (N:number)=>Promise<object>|object }} [opts] where finished stems are written
   *        (default: in memory). A fresh sink is requested for every attempt (e.g. after a WebGPU->WASM restart).
   * @returns {Promise<{sink: object, stems: Record<string,[Float32Array,Float32Array]>|null, backend: string, ms: number}>}
   */
  async separate(left, right, { onProgress, createSink } = {}) {
    if (!this.session) throw new Error('No model loaded');
    this.cancelled = false;
    const model = this.model;
    const adapter = ADAPTERS[model.adapter];
    const t0 = Date.now();
    const ort = this.ort;

    const attempt = async () => {
      const run = async (feeds) => {
        const inputs = {};
        for (const [name, { data, dims }] of Object.entries(feeds)) inputs[name] = new ort.Tensor('float32', data, dims);
        const res = await this.session.run(inputs);
        const out = {};
        for (const [name, tensor] of Object.entries(res)) {
          const d = tensor.data;
          out[name] = d instanceof Float32Array ? d.slice() : Float32Array.from(d);
          tensor.dispose?.();
        }
        for (const t of Object.values(inputs)) t.dispose?.();
        return out;
      };
      // WebGPU has silently produced all-zero / NaN output on some drivers & graphs.
      // Check the first non-silent chunk and bail out to WASM if it looks broken.
      const sanityCheck = this.backend !== 'webgpu' ? null : ({ stems }) => {
        let m = 0;
        for (const [l, r] of Object.values(stems)) m = Math.max(m, maxAbs(l), maxAbs(r));
        if (!(m > 1e-6) || !Number.isFinite(m)) {
          throw new BadGpuOutputError(`WebGPU produced silent/invalid output (max |x| = ${m})`);
        }
      };
      const sink = createSink ? await createSink(left.length) : undefined;
      try {
        return await separateTrack({
        adapter, run, left, right, sink, overlap: model.overlap, sanityCheck,
        isCancelled: () => this.cancelled,
        onChunk: (p) => onProgress?.({ phase: 'separate', backend: this.backend, ...p }),
        });
      } catch (e) { await sink?.dispose(); throw e; }
    };

    let result;
    try {
      result = await attempt();
    } catch (e) {
      if (e instanceof CancelledError || this.backend !== 'webgpu') throw e;
      await this.#switchToWasm(e.message || e, onProgress);
      result = await attempt();
    }
    return { sink: result.sink, stems: result.stems, backend: this.backend, ms: Date.now() - t0, chunks: result.chunks };
  }
}

export { CancelledError };
