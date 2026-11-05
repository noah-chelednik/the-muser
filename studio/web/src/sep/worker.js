/**
 * Module Web Worker: downloads/caches a model, runs STFT/overlap-add separation with onnxruntime-web,
 * and hands the finished stems back as transferable Float32Arrays.
 *
 * Messages in:  { type: 'load', modelId, device } | { type: 'separate', left, right } | { type: 'cancel' } | { type: 'release' }
 * Messages out: { type: 'progress', ... } | { type: 'loaded', ... } | { type: 'done', stems, ... } | { type: 'error', message, cancelled }
 */
import { MODELS, ORT_MODULE_URL, ORT_WASM_BASE, ORT_CDN_MODULE_URL, ORT_CDN_BASE } from './models.js';
import { RoformerEngine } from './engine.js';
import { getModelFiles } from './model-store.js';
import { MemorySink } from './sinks.js';

let engine = null;
let ortPromise = null;
let abort = null;

const post = (msg, transfer) => self.postMessage(msg, transfer || []);

async function importOrt() {
  try {
    const ort = await import(/* @vite-ignore */ ORT_MODULE_URL);
    ort.env.wasm.wasmPaths = ORT_WASM_BASE;
    const probe = await fetch(`${ORT_WASM_BASE}ort-wasm-simd-threaded.asyncify.wasm`, { method: 'HEAD' });
    if (!probe.ok) throw new Error(`ORT wasm: HTTP ${probe.status}`);
    return ort;
  } catch (e) {
    console.warn('[sep] same-origin onnxruntime-web unavailable, using the CDN:', e);
    const ort = await import(/* @vite-ignore */ ORT_CDN_MODULE_URL);
    ort.env.wasm.wasmPaths = ORT_CDN_BASE;
    return ort;
  }
}

async function loadOrt() {
  if (!ortPromise) {
    ortPromise = importOrt().then((ort) => {
      // Threads need SharedArrayBuffer, which needs cross-origin isolation (COOP/COEP). Without it: one thread, still SIMD.
      const isolated = self.crossOriginIsolated && typeof SharedArrayBuffer !== 'undefined';
      ort.env.wasm.numThreads = isolated ? Math.max(1, Math.min(navigator.hardwareConcurrency || 4, 8)) : 1;
      ort.env.wasm.proxy = false;
      ort.env.logLevel = 'error';
      return ort;
    });
  }
  return ortPromise;
}

async function getEngine() {
  if (!engine) {
    const ort = await loadOrt();
    engine = new RoformerEngine({
      ort,
      getModelFiles: (model, onProgress) => getModelFiles(model, onProgress, { signal: abort?.signal }),
      log: (...a) => console.warn('[sep]', ...a),
      webgpuAvailable: !!self.navigator?.gpu,
    });
  }
  return engine;
}

self.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    switch (msg.type) {
      case 'load': {
        abort = new AbortController();
        const eng = await getEngine();
        const info = await eng.load(msg.modelId, { device: msg.device, onProgress: (p) => post({ type: 'progress', ...p }) });
        post({ type: 'loaded', modelId: msg.modelId, ...info, threads: self.crossOriginIsolated ? 'multi' : 'single' });
        break;
      }
      case 'separate': {
        const eng = await getEngine();
        const model = MODELS[eng.model.id];
        const { sink, backend, ms } = await eng.separate(msg.left, msg.right, {
          createSink: (N) => new MemorySink(N),
          onProgress: (p) => post({ type: 'progress', ...p }),
        });
        const stems = {};
        const transfer = [];
        for (const name of model.stems) {
          if (!sink.data[name]) continue;
          stems[name] = sink.data[name];
          transfer.push(sink.data[name][0].buffer, sink.data[name][1].buffer);
        }
        post({ type: 'done', stems, backend, ms, sampleRate: model.sampleRate, frames: msg.left.length }, transfer);
        break;
      }
      case 'cancel':
        engine?.cancel();
        abort?.abort();
        break;
      case 'release':
        await engine?.unload();
        break;
      default:
        break;
    }
  } catch (e) {
    const cancelled = e?.name === 'CancelledError' || e?.name === 'AbortError';
    post({ type: 'error', cancelled, message: String(e?.message || e), name: e?.name });
  }
};
